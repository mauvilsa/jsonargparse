#!/usr/bin/env python3
# pragma: no cover
"""Generate argparse compatibility tests from CPython's test_argparse.py.

This script downloads the test_argparse.py file from the CPython repository,
transforms it to work with jsonargparse, and marks tests with pytest markers
to categorize compatibility differences.

The download is done with the GitHub CLI (gh). When gh is not installed, a test
file that is skipped is generated instead. When gh is installed but not
authenticated, generation fails.

Usage:
    python -m jsonargparse_tests.argparse_tests_generate [--python_version VERSION] [--output_file FILE]

Configuration:
    TestCategories class defines which tests from CPython's test_argparse.py should be marked
    with pytest markers to categorize compatibility differences.

    All marker assignments are declarative. Each category has a consistent structure:
      - classes: List of explicit class names
      - functions: List of explicit function names
      - class_patterns: List of patterns for class names (startswith matching)
      - function_patterns: List of patterns for function names (startswith matching)

    Tests can appear in multiple categories to receive multiple markers.
"""

import ast
import shutil
import subprocess  # nosec B404
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Literal, Union

# ============================================================================
# Test Categorization Configuration
# ============================================================================


class TestCategories:
    """Categorized test marking for argparse compatibility tests."""

    # Marker names for each category
    MARKER_NOT_SUPPORTED = "not_supported"
    MARKER_IMPLEMENTATION_SPECIFIC = "implementation_specific"
    MARKER_INVESTIGATE = "investigate"

    # Category A: Not Supported (intentional deviations from argparse)
    NOT_SUPPORTED: Dict[str, List[str]] = {
        "classes": [
            "TestParseKnownArgs",  # parse_known_args
            "TestAddSubparsers",  # subcommands
            "TestHelpSubparsersOrdering",  # subcommands
            "TestHelpSubparsersWithHelpOrdering",  # subcommands
            "TestTypeRegistration",  # type functions must be idempotent, get_my_type in test isn't
            "TestTypeUserDefined",  # conflicts with type hints support, class and subclasses
            "TestTypeClassicClass",  # conflicts with type hints support, class and subclasses
            "TestHelpUsageLongSubparserCommand",  # subcommands
        ],
        "functions": [
            "test_no_double_type_conversion_of_default",  # only idempotent functions supported
            "test_multiple_argument_option",  # parse_known_args
            "test_usage_long_subparser_command",  # subcommands
            "test_argparse_color",  # subcommands
            "test_wrong_argument_subparsers_with_suggestions",  # subcommands
            "test_wrong_argument_subparsers_no_suggestions",  # subcommands
        ],
        "class_patterns": [
            "TestFileType",  # deprecated
        ],
        "function_patterns": [
            "test_subparser",  # subcommands
            "test_help_subparser",  # subcommands
            "test_deprecated",  # deprecated
        ],
    }

    # Category B: Implementation-specific Tests
    # Tests that rely on argparse internals or specific implementation details
    IMPLEMENTATION_SPECIFIC: Dict[str, List[str]] = {
        "classes": [
            "TestTypeFunctionCallOnlyOnce",  # Type function calling behavior
            "TestHelpVariableExpansion",  # positional with default, useless argparse test?
        ],
        "functions": [
            "test_all_exports_everything_but_modules",  # Export checking
            "test_misc",  # TestActionsReturned::test_misc assert action.type fails
        ],
        "class_patterns": [],
        "function_patterns": [],
    }

    # Category C: Features to investigate
    # Tests that currently fail but might indicate compatibility issues to address
    INVESTIGATE: Dict[str, List[str]] = {
        "classes": [
            "TestOptionalsActionAppendConstWithDefault",
            "TestPositionalsActionAppend",
            "TestParserDefaultSuppress",
            "TestParserDefault42",
            "TestSetDefaults",
            "TestGetDefault",
            "TestArgumentTypeError",  # argparse prints '%(prog)s: error: %(message)s\n', jsonargparse skips prog
            "TestIntermixedArgs",  # uses parse_known_args
            "TestIntermixedMessageContentError",  # all required in error message, intermixed difference
            "TestHelpMetavarTypeFormatter",  # FIX! ActionTypeHint metavar as positional obtained action.type.__name__
            "TestPositionalsActionExtend",  # _ExtendAction
            "TestOptionalsNargsOptional",  # Sig('-z', nargs='?', type=int, const='42', default='84', choices=[1, 2])
            "TestPositionalsNargsZeroOrMoreDefault",  # Sig('foo', nargs='*', default='bar', choices=['a', 'b'])
            "TestPositionalsNargsOptionalDefault",  # Sig('foo', nargs='?', default=42, choices=['a', 'b'])
            "TestPositionalsNargsOptionalConvertedDefault",  # nargs='?', type=int, default='42', choices=[1, 2])
            "TestNegativeNumber",  # FIX! numbers with "_"
            "TestGroupConstructor",  # FIX! deprecated add_argument_group prefix_chars
        ],
        "functions": [
            "test_unrecognized_intermixed_args",  # uses parse_known_args
            "test_required_args_n_with_metavar",  # FIX! metavar shown in missing required
            "test_required_args_one_or_more_with_metavar",  # FIX! metavar shown in missing required
            "test_required_args_with_metavar",  # FIX! metavar shown in missing required
            "test_modified_invalid_action",  # raise ArgumentError/AssertionError instead of TypeError/ArgumentError
        ],
        "class_patterns": [],
        "function_patterns": [],
    }

    @classmethod
    def should_mark_class(cls, name: str) -> tuple[bool, list[tuple[str, str]]]:
        """Check if a class should be marked and return (should_mark, [(category, marker_name), ...])."""
        markers = []

        # Check each category
        categories = [
            ("not_supported", cls.NOT_SUPPORTED, cls.MARKER_NOT_SUPPORTED),
            ("implementation_specific", cls.IMPLEMENTATION_SPECIFIC, cls.MARKER_IMPLEMENTATION_SPECIFIC),
            ("investigate", cls.INVESTIGATE, cls.MARKER_INVESTIGATE),
        ]

        for category_name, category_data, marker in categories:
            # Check explicit class names
            if name in category_data.get("classes", []):
                markers.append((f"{category_name}:explicit", marker))

            # Check class patterns (startswith matching)
            for pattern in category_data.get("class_patterns", []):
                if name.startswith(pattern):
                    markers.append((f"{category_name}:{pattern}_pattern", marker))
                    break  # Only match once per category

        return len(markers) > 0, markers

    @classmethod
    def should_mark_function(cls, name: str) -> tuple[bool, list[tuple[str, str]]]:
        """Check if a function should be marked and return (should_mark, [(category, marker_name), ...])."""
        markers = []

        # Check each category
        categories = [
            ("not_supported", cls.NOT_SUPPORTED, cls.MARKER_NOT_SUPPORTED),
            ("implementation_specific", cls.IMPLEMENTATION_SPECIFIC, cls.MARKER_IMPLEMENTATION_SPECIFIC),
            ("investigate", cls.INVESTIGATE, cls.MARKER_INVESTIGATE),
        ]

        for category_name, category_data, marker in categories:
            # Check explicit function names
            if name in category_data.get("functions", []):
                markers.append((f"{category_name}:explicit", marker))

            # Check function patterns (startswith matching)
            for pattern in category_data.get("function_patterns", []):
                if name.startswith(pattern):
                    markers.append((f"{category_name}:{pattern}_pattern", marker))
                    break  # Only match once per category

        return len(markers) > 0, markers


# Import replacement code to inject at the top of the test file
IMPORT_REPLACEMENT = """
import pytest
import argparse as _argparse
import jsonargparse as argparse

# Use argparse classes for formatters and other utilities that jsonargparse doesn't override
for attr in [
    "Action",
    "ArgumentTypeError",
    "FileType",
    "RawTextHelpFormatter",
    "RawDescriptionHelpFormatter",
    "ArgumentDefaultsHelpFormatter",
    "MetavarTypeHelpFormatter",
    "HelpFormatter",
    "BooleanOptionalAction",
    "ONE_OR_MORE",
    "OPTIONAL",
    "REMAINDER",
    "SUPPRESS",
    "ZERO_OR_MORE",
]:
    if hasattr(_argparse, attr):
        setattr(argparse, attr, getattr(_argparse, attr))

# Shorthand pytest markers for categorizing compatibility differences
not_supported = pytest.mark.not_supported(reason="Intentional deviation from argparse")
implementation_specific = pytest.mark.implementation_specific(reason="Tests argparse internals")
investigate = pytest.mark.investigate(reason="Potential compatibility issue")

# Custom ArgumentParser class that uses argparse.HelpFormatter by default
class ArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, formatter_class=_argparse.HelpFormatter, **kwargs):
        super().__init__(*args, formatter_class=formatter_class, **kwargs)

argparse.ArgumentParser = ArgumentParser
"""


I18N_HELPER_IMPORT_REPLACEMENT = """
try:
    from test.support.i18n_helper import TestTranslationsBase, update_translation_snapshots
except ImportError:
    class TestTranslationsBase(unittest.TestCase):
        def setUp(self):
            self.skipTest(\"test.support.i18n_helper unavailable in this Python installation\")

    def update_translation_snapshots(module):
        raise RuntimeError(\"test.support.i18n_helper unavailable in this Python installation\")
"""


GH_UNAVAILABLE_MESSAGE = (
    "The GitHub CLI (gh) is required to download CPython's test_argparse.py. "
    "See https://cli.github.com for how to install it, and run 'gh auth login' "
    "to authenticate."
)

# Generated instead of the tests when gh is not installed, such that test runs
# report a skip instead of failing. A collected test is required because pytest
# exits with a failure status when no tests are collected.
GH_UNAVAILABLE_TESTS = f'''"""Placeholder for the argparse compatibility tests, which could not be generated."""

import pytest


@pytest.mark.skip(reason={GH_UNAVAILABLE_MESSAGE!r})
def test_argparse_compatibility_not_generated():
    pass
'''


# ============================================================================
# AST Transformation
# ============================================================================


class ArgparseTestTransformer(ast.NodeTransformer):
    """Transform CPython's test_argparse.py to work with jsonargparse."""

    def __init__(self):
        self.marked_tests: Dict[str, List[str]] = defaultdict(list)
        self.total_classes = 0
        self.total_functions = 0
        self.marked_classes = 0
        self.marked_functions = 0

    @staticmethod
    def add_marker_decorator(node: Union[ast.ClassDef, ast.FunctionDef], marker_name: str) -> None:
        """Add a pytest marker decorator to a class or function node.

        Args:
            node: AST class or function definition node
            marker_name: Name of the marker (e.g., 'not_supported')
        """
        # Create a simple name decorator: @marker_name
        decorator = ast.Name(id=marker_name, ctx=ast.Load())
        node.decorator_list.append(decorator)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        """Visit class definitions and add markers based on configuration."""
        self.total_classes += 1
        should_mark, markers = TestCategories.should_mark_class(node.name)

        if should_mark:
            self.marked_classes += 1
            # Collect all markers for reporting
            for category, marker_name in markers:
                self.marked_tests[category].append(f"class {node.name}")
            # Apply all marker decorators
            for category, marker_name in markers:
                self.add_marker_decorator(node, marker_name)

        # Continue visiting child nodes
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        """Visit function definitions and add markers based on configuration."""
        self.total_functions += 1
        should_mark, markers = TestCategories.should_mark_function(node.name)

        if should_mark:
            self.marked_functions += 1
            # Collect all markers for reporting
            for category, marker_name in markers:
                self.marked_tests[category].append(f"function {node.name}")
            # Apply all marker decorators
            for category, marker_name in markers:
                self.add_marker_decorator(node, marker_name)

        return node

    def visit_If(self, node: ast.If) -> Any:
        """Visit if statements and filter out if __name__ == '__main__' block."""
        if isinstance(node.test, ast.Compare):
            left = node.test.left
            if isinstance(left, ast.Name) and left.id == "__name__":
                return None
        return node

    def generate_report(self) -> str:
        """Generate a detailed test marking report."""
        unmarked = self.total_classes + self.total_functions - self.marked_classes - self.marked_functions
        report_lines = [
            "=" * 70,
            "Argparse Compatibility Test Report",
            "=" * 70,
            f"Python Version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "",
            "Statistics:",
            f"  Total Test Classes: {self.total_classes}",
            f"  Total Test Functions: {self.total_functions}",
            f"  Marked Classes: {self.marked_classes}",
            f"  Marked Functions: {self.marked_functions}",
            f"  Unmarked (Compatible): {unmarked}",
            "",
            "Marked Tests by Category:",
            "(Tests marked with pytest markers for categorization)",
        ]

        for reason, tests in sorted(self.marked_tests.items()):
            report_lines.append(f"\n  {reason}: {len(tests)} tests")
            for test in sorted(tests)[:10]:  # Show first 10
                report_lines.append(f"    - {test}")
            if len(tests) > 10:
                report_lines.append(f"    ... and {len(tests) - 10} more")

        report_lines.extend(
            [
                "",
                "=" * 70,
                "",
                "Marker Categories:",
                "  - not_supported: Intentional deviations from argparse",
                "  - implementation_specific: Tests relying on argparse internals",
                "  - investigate: Potential compatibility issues to address",
                "",
                "By default, marked tests are skipped. Run with pytest -m to select specific categories.",
                "Examples:",
                "  pytest -m investigate tests_argparse.py  # Run only investigate tests",
                "  pytest -m 'not not_supported' tests_argparse.py  # Run all except not_supported tests",
                "",
                "To avoid unknown marker warnings, add:  -W ignore::pytest.PytestUnknownMarkWarning",
                "To avoid tracebacks of failed tests, add:  --tb=no",
                "",
            ]
        )

        return "\n".join(report_lines)


def download_test_file(python_version: str, verbose: bool = False) -> str:
    """Download test_argparse.py from CPython repository using the GitHub CLI.

    Args:
        python_version: Python version tag (e.g., "3.12.0")
        verbose: Whether to print verbose output

    Returns:
        Content of test_argparse.py

    Raises:
        RuntimeError: If download fails, e.g. gh not authenticated
    """
    tag = f"v{python_version}"
    endpoint = f"repos/python/cpython/contents/Lib/test/test_argparse.py?ref={tag}"
    command = ["gh", "api", endpoint, "--header", "Accept: application/vnd.github.raw"]

    if verbose:
        print(f"Downloading with: {' '.join(command)}")

    try:
        process = subprocess.run(command, capture_output=True, check=True, timeout=60)  # nosec B603
    except subprocess.CalledProcessError as ex:
        stderr = ex.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"'{' '.join(command)}' failed with status {ex.returncode}: {stderr}") from ex
    except (OSError, subprocess.SubprocessError) as ex:
        raise RuntimeError(f"'{' '.join(command)}' failed: {ex}") from ex

    return process.stdout.decode("utf-8")


def replace_import_in_ast(tree: ast.Module) -> ast.Module:
    """Replace 'import argparse' with IMPORT_REPLACEMENT in the AST.

    Args:
        tree: AST tree

    Returns:
        Modified AST tree
    """
    # Find and replace the import statement
    for i, node in enumerate(tree.body):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "argparse" and alias.asname is None:
                    # Replace with the import replacement code
                    replacement_tree = ast.parse(IMPORT_REPLACEMENT)
                    tree.body[i : i + 1] = replacement_tree.body
                    break
    return tree


def replace_i18n_helper_import_in_ast(tree: ast.Module) -> ast.Module:
    """Replace the i18n helper import with a guarded fallback.

    Python 3.13+ stdlib test.support.i18n_helper can depend on CPython source-tree
    modules that are not installed system-wide. Guard the import so test collection
    still works outside a CPython checkout.

    Args:
        tree: AST tree

    Returns:
        Modified AST tree
    """
    for i, node in enumerate(tree.body):
        if isinstance(node, ast.ImportFrom) and node.module == "test.support.i18n_helper":
            replacement_tree = ast.parse(I18N_HELPER_IMPORT_REPLACEMENT)
            tree.body[i : i + 1] = replacement_tree.body
            break
    return tree


def transform_test_file(source_code: str) -> tuple[str, ArgparseTestTransformer]:
    """Transform the test file to work with jsonargparse.

    Args:
        source_code: Source code of the original CPython test_argparse.py content

    Returns:
        Tuple of (transformed code, transformer with statistics)
    """
    source_code = source_code.replace("TestHelpFormattingMetaclass", "HelpFormattingMetaclass")
    tree = ast.parse(source_code)

    # Replace import statement in AST
    tree = replace_import_in_ast(tree)
    tree = replace_i18n_helper_import_in_ast(tree)

    # Apply test markers
    transformer = ArgparseTestTransformer()
    transformed_tree = transformer.visit(tree)

    # Fix missing locations (required for code generation)
    ast.fix_missing_locations(transformed_tree)

    # Generate code from transformed AST
    final_code = ast.unparse(transformed_tree)

    return final_code, transformer


def generate_tests(
    python_version: Union[str, Literal["current"]] = "current",
    keep_original: bool = False,
    output_file: str = "tests_argparse.py",
    verbose: bool = True,
) -> None:
    """Generate argparse compatibility tests.

    Args:
        python_version: Python version to download tests for
        keep_original: Whether to keep the original argparse test file
        output_file: Name of the generated test file to write in the current directory
        verbose: Whether to print verbose output
    """

    def print_verbose(message: str) -> None:
        if verbose:
            print(message)

    if python_version == "current":
        # Use current Python version
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    # Output to current working directory
    output_dir = Path.cwd()
    original_file = output_dir / "argparse_tests_original.py"
    generated_file = output_dir / output_file

    # Check if generated file already exists
    if generated_file.exists():
        print(f"Generated test file already exists: {generated_file}", file=sys.stderr)
        print(f"To regenerate, remove {generated_file} and run this command again.", file=sys.stderr)
        return

    # Without gh there is no way to download, so generate tests that are skipped
    if not shutil.which("gh"):
        print(GH_UNAVAILABLE_MESSAGE, file=sys.stderr)
        print(f"Generating skipped test file: {generated_file}", file=sys.stderr)
        generated_file.write_text(GH_UNAVAILABLE_TESTS)
        return

    # Download test file
    print_verbose(f"Downloading test_argparse.py for Python {python_version}...")
    try:
        source_code = download_test_file(python_version, verbose=verbose)
    except RuntimeError as ex:
        print(f"Failed to download test file: {ex}", file=sys.stderr)
        sys.exit(1)

    # Normalize the original file by parsing and unparsing through AST
    # This ensures both original and transformed files have the same AST-induced changes
    # (quote normalization, comment removal, etc.) so diffs only show actual transformations
    print_verbose("Normalizing original file through AST parse/unparse...")
    try:
        # Parse and unparse to normalize
        tree = ast.parse(source_code)
        ast.fix_missing_locations(tree)
        normalized_code = ast.unparse(tree)
        # Save normalized original
        if keep_original:
            original_file.write_text(normalized_code)
            print_verbose(f"Saved normalized original to: {original_file}")
    except SyntaxError as ex:
        print(f"Error parsing original file: {ex}", file=sys.stderr)
        sys.exit(1)

    # Transform the test file
    print_verbose("Transforming test file...")
    try:
        transformed_code, transformer = transform_test_file(source_code)
    except SyntaxError as ex:
        print(f"Error parsing test file: {ex}", file=sys.stderr)
        sys.exit(1)

    # Validate generated code
    try:
        compile(transformed_code, str(generated_file), "exec")
    except SyntaxError as ex:
        print(f"Error: Generated code has syntax errors: {ex}", file=sys.stderr)
        sys.exit(1)

    # Write generated test file
    generated_file.write_text(transformed_code)
    print_verbose(f"Generated test file: {generated_file}")

    # Generate and print report
    report = transformer.generate_report()
    print_verbose("\n" + report)


if __name__ == "__main__":
    from jsonargparse import auto_cli

    auto_cli(generate_tests)
