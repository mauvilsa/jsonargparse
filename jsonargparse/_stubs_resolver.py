import ast
import inspect
import sys
from contextlib import suppress
from copy import deepcopy
from importlib import import_module
from typing import TYPE_CHECKING, Any

from ._common import get_parsing_setting
from ._optionals import import_typeshed_client, typeshed_client_support
from ._postponed_annotations import NamesVisitor, get_arg_type

if TYPE_CHECKING:  # pragma: no cover
    import typeshed_client as tc
else:
    tc = import_typeshed_client()


kinds = inspect._ParameterKind


def import_module_or_none(path: str):
    if path.endswith(".__init__"):
        path = path[:-9]
    try:
        return import_module(path)
    except ModuleNotFoundError:
        return None


class ImportsVisitor(ast.NodeVisitor):
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            module_path = self.module_path[: -node.level]
            if node.module:
                module_path.append(node.module)
            node = deepcopy(node)
            node.module = ".".join(module_path)
            node.level = 0
        for alias in node.names:
            self.imports_found[alias.asname or alias.name] = (node.module, alias.name)

    def find(self, node: ast.AST, module_path: str) -> dict[str, tuple[str | None, str]]:
        self.module_path = module_path.split(".")
        self.imports_found: dict[str, tuple[str | None, str]] = {}
        self.visit(node)
        return self.imports_found


def ast_annassign_to_assign(node: ast.AnnAssign) -> ast.Assign:
    return ast.Assign(
        targets=[node.target],
        value=node.value,  # type: ignore[arg-type]
        lineno=node.lineno,
        end_lineno=node.lineno,
    )


class AssignsVisitor(ast.NodeVisitor):
    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if hasattr(target, "id"):
                self.assigns_found[target.id] = node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if hasattr(node.target, "id"):
            self.assigns_found[node.target.id] = ast_annassign_to_assign(node)

    def find(self, node: ast.AST) -> dict[str, ast.Assign]:
        self.assigns_found: dict[str, ast.Assign] = {}
        self.visit(node)
        return self.assigns_found


class MethodsVisitor(ast.NodeVisitor):
    method_found: ast.FunctionDef | None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not self.method_found and node.name == self.method_name:
            self.method_found = node

    def visit_If(self, node: ast.If) -> None:
        test_ast = ast.parse("___test___ = 0")
        test_ast.body[0].value = node.test  # type: ignore[attr-defined]
        exec_vars = {"sys": sys}
        with suppress(Exception):
            exec(compile(test_ast, filename="<ast>", mode="exec"), exec_vars, exec_vars)
            if exec_vars["___test___"]:
                node.orelse = []
            else:
                node.body = []
            self.generic_visit(node)

    def find(self, node: ast.AST, method_name: str) -> ast.FunctionDef | None:
        self.method_name = method_name
        self.method_found = None
        self.visit(node)
        return self.method_found


stubs_resolver = None


def get_stubs_resolver():
    global stubs_resolver
    if not stubs_resolver:
        allow_py_files = get_parsing_setting("stubs_resolver_allow_py_files")
        search_context = tc.get_search_context(allow_py_files=allow_py_files)
        stubs_resolver = StubsResolver(search_context=search_context)
    return stubs_resolver


def get_mro_method_parent(parent, method_name):
    while hasattr(parent, "__dict__") and method_name not in parent.__dict__:
        try:
            parent = inspect.getmro(parent)[1]
        except IndexError:
            parent = None
    return None if parent is object else parent


def get_source_module(path: str, component) -> tc.ModulePath:
    if component is None:
        module_path, name = path.rsplit(".", 1)
        component = getattr(import_module_or_none(module_path), name, None)
    if component is not None:
        module = inspect.getmodule(component)
        assert module is not None
        module_path = module.__name__
        if getattr(module, "__file__", "").endswith("__init__.py"):
            module_path += ".__init__"
    return tc.ModulePath(tuple(module_path.split(".")))


class StubsResolver(tc.Resolver):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._module_ast_cache: dict[str, ast.AST | None] = {}
        self._module_assigns_cache: dict[str, dict[str, ast.Assign]] = {}
        self._module_imports_cache: dict[str, dict[str, tuple[str | None, str]]] = {}

    def get_imported_info(self, path: str, component=None) -> tc.ImportedInfo | None:
        resolved = self.get_fully_qualified_name(path)
        imported_info = None
        if isinstance(resolved, tc.ImportedInfo):
            imported_info = resolved
        elif isinstance(resolved, tc.NameInfo):
            source_module = get_source_module(path, component)
            imported_info = tc.ImportedInfo(source_module=source_module, info=resolved)
        return imported_info

    def get_component_imported_info(self, component, parent) -> tc.ImportedInfo | None:
        if not parent and inspect.ismethod(component):
            parent = type(component.__self__)
            component = getattr(parent, component.__name__)
        if not parent:
            return self.get_imported_info(f"{component.__module__}.{component.__name__}", component)
        parent = get_mro_method_parent(parent, component.__name__)
        stub_import = parent and self.get_imported_info(f"{parent.__module__}.{parent.__name__}", component)
        if stub_import and isinstance(stub_import.info.ast, ast.AST):
            method_ast = MethodsVisitor().find(stub_import.info.ast, component.__name__)
            assert method_ast
            name_info = tc.NameInfo(name=component.__qualname__, is_exported=False, ast=method_ast)
            stub_import = tc.ImportedInfo(source_module=stub_import.source_module, info=name_info)
        return stub_import

    def get_aliases(self, imported_info: tc.ImportedInfo):
        aliases: dict[str, tuple[str, Any]] = {}
        self.add_import_aliases(aliases, imported_info)
        return aliases

    def get_module_stub_ast(self, module_path: str):
        if module_path not in self._module_ast_cache:
            self._module_ast_cache[module_path] = tc.get_stub_ast(module_path, search_context=self.ctx)
        return self._module_ast_cache[module_path]

    def get_module_stub_assigns(self, module_path: str):
        if module_path not in self._module_assigns_cache:
            module_ast = self.get_module_stub_ast(module_path)
            self._module_assigns_cache[module_path] = AssignsVisitor().find(module_ast)
        return self._module_assigns_cache[module_path]

    def get_module_stub_imports(self, module_path: str):
        if module_path not in self._module_imports_cache:
            module_ast = self.get_module_stub_ast(module_path)
            self._module_imports_cache[module_path] = ImportsVisitor().find(module_ast, module_path)
        return self._module_imports_cache[module_path]

    def add_import_aliases(self, aliases, stub_import: tc.ImportedInfo):
        module_path = ".".join(stub_import.source_module)
        module = import_module_or_none(module_path)
        stub_ast: ast.AST | None = None
        if isinstance(stub_import.info.ast, (ast.Assign, ast.AnnAssign)):
            stub_ast = stub_import.info.ast.value
        elif isinstance(stub_import.info.ast, ast.AST):
            stub_ast = stub_import.info.ast
        if stub_ast:
            self.add_module_aliases(aliases, module_path, module, stub_ast)
        return module_path, stub_import.info.ast

    def add_module_aliases(self, aliases, module_path, module, node, skip=set()):
        names = NamesVisitor().find(node) if node else []
        for name in names:
            if alias_already_added(aliases, name, module_path) or name in skip:
                continue
            source = module_path
            if name in __builtins__:
                source = "__builtins__"
                value = __builtins__[name]
            elif hasattr(module, name):
                value = getattr(module, name)
            elif name in self.get_module_stub_assigns(module_path):
                value = self.get_module_stub_assigns(module_path)[name]
                self.add_module_aliases(aliases, module_path, module, value.value, skip={name})
            elif name in self.get_module_stub_imports(module_path):
                imported_module_path, imported_name = self.get_module_stub_imports(module_path)[name]
                imported_module = import_module_or_none(imported_module_path)
                if hasattr(imported_module, imported_name):
                    source = imported_module_path
                    value = getattr(imported_module, imported_name)
                else:
                    stub_import = self.get_imported_info(f"{imported_module_path}.{imported_name}")
                    source, value = self.add_import_aliases(aliases, stub_import)
            else:
                value = NotImplementedError(f"{name!r} from {module_path!r} not in builtins, module or stub")
            if alias_already_added(aliases, name, source):
                continue
            if not alias_is_unique(aliases, name, source, value):
                value = NotImplementedError(
                    f"non-unique alias {name!r}: {aliases[name][1]} ({aliases[name][0]}) vs {value} ({source})"
                )
            aliases[name] = (source, value)


def alias_already_added(aliases, name, source):
    return name in aliases and aliases[name][0] in {"__builtins__", source}


def alias_is_unique(aliases, name, source, value):
    if name in aliases:
        src, val = aliases[name]
        if src != source:
            return val is value
    return True


def get_stub_types(params, component, parent, logger) -> dict[str, Any] | None:
    if not typeshed_client_support:
        return None
    missing_types = {
        p.name: n
        for n, p in enumerate(params)
        if p.kind not in {kinds.VAR_POSITIONAL, kinds.VAR_KEYWORD} and p.annotation == inspect._empty
    }
    if not missing_types:
        return None
    resolver = get_stubs_resolver()
    stub_import = resolver.get_component_imported_info(component, parent)
    if not stub_import:
        return None
    known_params = {p.name for p in params}
    aliases = resolver.get_aliases(stub_import)
    arg_asts = stub_import.info.ast.args.args + stub_import.info.ast.args.kwonlyargs
    types = {}
    for arg_ast in arg_asts[1:] if parent else arg_asts:
        name = arg_ast.arg
        if arg_ast.annotation and (name in missing_types or name not in known_params):
            try:
                types[name] = get_arg_type(arg_ast.annotation, aliases)
            except Exception as ex:
                logger.debug(
                    f"Failed to parse type stub for {component.__qualname__!r} parameter {name!r}", exc_info=ex
                )
                if name not in known_params:
                    types[name] = inspect._empty
    return types


def get_stub_return_type(function, logger) -> Any:
    """Returns the return type of a function from its stub, or None if not found."""
    if not typeshed_client_support:
        return None
    resolver = get_stubs_resolver()
    stub_import = resolver.get_component_imported_info(function, None)
    if not stub_import or not stub_import.info.ast.returns:
        return None
    try:
        return get_arg_type(stub_import.info.ast.returns, resolver.get_aliases(stub_import))
    except Exception as ex:
        if logger:
            logger.debug(f"Failed to parse type stub for {function.__qualname__!r} return type", exc_info=ex)
        return None
