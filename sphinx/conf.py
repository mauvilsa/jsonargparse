# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

os.environ["SPHINX_BUILD"] = ""


# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "jsonargparse"
copyright = "2019-present, Mauricio Villegas"
author = "Mauricio Villegas"


# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "autodocsumm",
    "sphinx_autodoc_typehints",
]

templates_path = []
exclude_patterns = ["_build"]


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
html_static_path = []


# -- autodoc

sys.path.insert(0, os.path.abspath("../"))

autodoc_default_options = {
    "members": True,
    "exclude-members": "groups",
    "member-order": "bysource",
    "show-inheritance": True,
    "autosummary": True,
    "autosummary-imported-members": False,
    "special-members": "__init__,__call__",
}


# -- doctest

import doctest  # noqa: E402

IGNORE_RESULT = doctest.register_optionflag("IGNORE_RESULT")

OutputChecker = doctest.OutputChecker


class CustomOutputChecker(OutputChecker):
    def check_output(self, want, got, optionflags):
        if IGNORE_RESULT & optionflags:
            return True
        return OutputChecker.check_output(self, want, got, optionflags)


doctest.OutputChecker = CustomOutputChecker

doctest_global_setup = """
import os
import pathlib
import shutil
import sys
import tempfile
from calendar import Calendar
from dataclasses import dataclass
from io import StringIO
from typing import Callable, Iterable, Protocol
import jsonargparse_tests
from jsonargparse import *
from jsonargparse import _common
from jsonargparse.typing import *
from jsonargparse._util import unresolvable_import_paths

def doctest_mock_class_in_main(cls):
    cls.__module__ = None
    setattr(sys.modules["__main__"], cls.__name__, cls)
    unresolvable_import_paths[cls] = f"__main__.{cls.__name__}"
"""


# -- intersphinx

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}
