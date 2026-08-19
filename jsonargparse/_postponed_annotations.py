import ast
import inspect
import logging
import sys
import textwrap
from dataclasses import is_dataclass
from importlib import import_module
from types import UnionType
from typing import Any, ForwardRef, TypeAlias, TypeVar, Union, get_type_hints

from ._typehints import mapping_origin_types, sequence_origin_types, tuple_set_origin_types
from ._util import get_typehint_origin

_TRIGGER_MODULE_CACHE_MAXSIZE = 1024
_TRIGGER_MODULE_CACHE: dict[int, dict[str, Any]] = {}
_MODULE_TYPE_CHECKING_CACHE: dict[str, tuple[dict, dict]] = {}


class NamesVisitor(ast.NodeVisitor):
    def visit_Name(self, node: ast.Name) -> None:
        self.names_found.append(node.id)

    def find(self, node: ast.AST) -> list:
        from ._util import unique

        self.names_found: list[str] = []
        self.visit(node)
        self.names_found = unique(self.names_found)
        return self.names_found


class TypeCheckingVisitor(ast.NodeVisitor):
    type_checking_names: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "typing":
                name = ast.dump(
                    ast.Attribute(
                        value=ast.Name(id=alias.asname or "typing", ctx=ast.Load()),
                        attr="TYPE_CHECKING",
                        ctx=ast.Load(),
                    )
                )
                self.type_checking_names.append(name)
                break

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "typing":
            for alias in node.names:
                if alias.name == "TYPE_CHECKING":
                    name = ast.dump(ast.Name(id=alias.asname or "TYPE_CHECKING", ctx=ast.Load()))
                    self.type_checking_names.append(name)
                    break

    def visit_If(self, node: ast.If) -> None:
        if (
            isinstance(node.test, (ast.Name, ast.Attribute))
            and any(ast.dump(node.test) == n for n in self.type_checking_names)
        ) or (
            isinstance(node.test, ast.BoolOp)
            and isinstance(node.test.op, (ast.And, ast.Or))
            and any(ast.dump(v) == n for n in self.type_checking_names for v in node.test.values)
        ):
            ast_exec = ast.parse("")
            ast_exec.body = node.body
            try:
                exec(compile(ast_exec, filename="<ast>", mode="exec"), self.aliases, self.aliases)
            except Exception as ex:
                if self.logger:
                    self.logger.debug(f"Failed to execute 'TYPE_CHECKING' block in '{self.module}'", exc_info=ex)

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, (ast.If, ast.Module)):
            super().generic_visit(node)

    def update_aliases(
        self, module_source: str, module: str, aliases: dict, logger: logging.Logger | None = None
    ) -> None:
        self.module = module
        self.aliases = aliases
        self.logger = logger
        module_tree = ast.parse(module_source)
        self.visit(module_tree)


def get_arg_type(arg_ast, aliases):
    type_ast = ast.parse("___arg_type___ = 0")
    type_ast.body[0].value = arg_ast
    exec_vars = {}
    bad_aliases = {}
    add_asts = False
    for name in NamesVisitor().find(arg_ast):
        value = aliases[name]
        if isinstance(value, tuple):
            value = value[1]
        if isinstance(value, Exception):
            bad_aliases[name] = value
        elif isinstance(value, ast.AST):
            add_asts = True
        else:
            exec_vars[name] = value
    if add_asts:
        body = []
        for name, (_, value) in aliases.items():
            if isinstance(value, ast.AST):
                body.append(ast.fix_missing_locations(value))
            elif not isinstance(value, Exception):
                exec_vars[name] = value
        type_ast.body = body + type_ast.body
        if "TypeAlias" not in exec_vars:
            exec_vars["TypeAlias"] = TypeAlias
    try:
        exec(compile(type_ast, filename="<ast>", mode="exec"), exec_vars, exec_vars)
    except NameError as ex:
        ex_from = None
        for name, alias_exception in bad_aliases.items():
            if str(ex) == f"name '{name}' is not defined":
                ex_from = alias_exception
                break
        raise ex from ex_from
    return exec_vars["___arg_type___"]


def resolve_forward_refs(arg_type, aliases, logger):
    def resolve_subtypes_forward_refs(typehint):
        if has_subtypes(typehint):
            try:
                subtypes = []
                for arg in typehint.__args__:
                    if isinstance(arg, (ForwardRef, str)):
                        forward_arg = arg.__forward_arg__ if isinstance(arg, ForwardRef) else arg
                        forward_arg, *_ = forward_arg.split(".", 1)
                        if forward_arg in aliases:
                            arg = aliases[forward_arg]
                        else:
                            raise NameError(f"Name '{forward_arg}' is not defined")
                    else:
                        arg = resolve_subtypes_forward_refs(arg)
                    subtypes.append(arg)
                if subtypes != list(typehint.__args__):
                    typehint_origin = get_typehint_origin(typehint)
                    typehint = typehint_origin[tuple(subtypes)]
            except Exception as ex:
                if logger:
                    logger.debug(f"Failed to resolve forward refs in {typehint}", exc_info=ex)
        return typehint

    return resolve_subtypes_forward_refs(arg_type)


def has_subtypes(typehint):
    typehint_origin = get_typehint_origin(typehint)
    if typehint_origin is type and hasattr(typehint, "__args__"):
        return True

    return (
        typehint_origin == Union
        or typehint_origin in sequence_origin_types
        or typehint_origin in tuple_set_origin_types
        or typehint_origin in mapping_origin_types
    )


def type_requires_eval(typehint):
    if has_subtypes(typehint):
        return any(type_requires_eval(a) for a in getattr(typehint, "__args__", []))
    return isinstance(typehint, (str, ForwardRef))


def type_uses_stand_in(typehint, stand_ins: dict) -> bool:
    """Whether a type was evaluated against a TYPE_CHECKING stand-in, so it must be resolved again."""
    if not stand_ins:
        return False
    if any(typehint is stand_in for stand_in in stand_ins.values()):
        return True
    # only a tuple is the subtypes of a type hint, e.g. types.UnionType has __args__ as a slot descriptor
    subtypes = getattr(typehint, "__args__", None)
    return isinstance(subtypes, tuple) and any(type_uses_stand_in(a, stand_ins) for a in subtypes)


def _collect_string_fwd_ref_names(typehint: Any, result: set[str]) -> None:
    if isinstance(typehint, str):
        result.add(typehint.split(".")[0])
    elif isinstance(typehint, ForwardRef):
        result.add(typehint.__forward_arg__.split(".")[0])
    elif has_subtypes(typehint):
        for arg in getattr(typehint, "__args__", ()):
            _collect_string_fwd_ref_names(arg, result)


def _update_missing_from_module_vars(global_vars: dict, missing: set[str], mod_vars: dict[str, Any]) -> None:
    for name in missing.copy():
        if name in mod_vars:
            global_vars[name] = mod_vars[name]
            missing.discard(name)


def _cache_trigger_bindings(trigger_id: int, mod_vars: dict[str, Any], names: set[str]) -> None:
    cached_bindings = _TRIGGER_MODULE_CACHE.get(trigger_id)
    if cached_bindings is None:
        if _TRIGGER_MODULE_CACHE_MAXSIZE > 0 and len(_TRIGGER_MODULE_CACHE) >= _TRIGGER_MODULE_CACHE_MAXSIZE:
            del _TRIGGER_MODULE_CACHE[next(iter(_TRIGGER_MODULE_CACHE))]
        cached_bindings = {}
        _TRIGGER_MODULE_CACHE[trigger_id] = cached_bindings
    for name in names:
        if name in mod_vars:
            cached_bindings[name] = mod_vars[name]


def _enrich_globals_for_string_forward_refs(global_vars: dict[str, Any]) -> None:
    """Add to global_vars types referenced as string forward refs in generic aliases but missing from it.

    Handles the case where a generic alias such as ``list["ForwardReferenced"]`` was defined in
    module A and imported into module B, but ``ForwardReferenced`` was not imported into module B.
    """
    # Collect all string/ForwardRef names nested inside generic alias args
    needed: set[str] = set()
    trigger_value_ids: set[int] = set()
    for value in global_vars.values():
        # Only consider generic/type-hint-like values (with subtypes) or ForwardRef.
        # Avoid treating arbitrary string globals (e.g., __name__, __doc__) as forward refs.
        if not (hasattr(value, "__args__") or isinstance(value, ForwardRef)):
            continue
        before = len(needed)
        _collect_string_fwd_ref_names(value, needed)
        if len(needed) > before:
            trigger_value_ids.add(id(value))

    missing = needed - set(global_vars.keys())
    if not missing:
        return

    # Reuse the previously discovered bindings before scanning sys.modules again.
    for trigger_id in trigger_value_ids:
        cached_bindings = _TRIGGER_MODULE_CACHE.get(trigger_id, {})
        _update_missing_from_module_vars(global_vars, missing, cached_bindings)

    if not missing:
        return

    # Find candidate modules: those that define the same trigger values (by identity).
    # This lets us trace generic aliases back to their origin module.
    for mod in sys.modules.values():
        if mod is None or not missing:
            continue
        try:
            mod_vars = vars(mod)
        except TypeError:
            continue
        matched_trigger_ids = {id(value) for value in mod_vars.values() if id(value) in trigger_value_ids}
        if not matched_trigger_ids:
            continue
        for trigger_id in matched_trigger_ids:
            _cache_trigger_bindings(trigger_id, mod_vars, needed)
        _update_missing_from_module_vars(global_vars, missing, mod_vars)


def get_module_type_checking_names(module: str, logger: logging.Logger | None = None) -> tuple[dict, dict]:
    """Returns the names that the TYPE_CHECKING blocks of a module bind, and the stand-ins of those names.

    A stand-in is the runtime value of a name that a TYPE_CHECKING block binds
    to a different object, e.g. ``else: Name = Any``. Since the runtime value is
    only there to make the module importable, a type evaluated against it is
    silently wrong and must be resolved again from the source.

    Both dicts are empty for a module without TYPE_CHECKING blocks. The result
    is cached because parsing a module is expensive and neither its source nor
    its availability change, though not for a module that is not imported,
    since it could be imported later on.
    """
    if module in _MODULE_TYPE_CHECKING_CACHE:
        return _MODULE_TYPE_CHECKING_CACHE[module]
    names: dict = {}
    stand_ins: dict = {}
    module_obj = sys.modules.get(module)
    if module_obj is None:
        return names, stand_ins
    try:
        module_source = inspect.getsource(module_obj)
        if "TYPE_CHECKING" in module_source:
            module_vars = vars(module_obj)
            # the block is executed in the namespace of its own module, so that it can use its names
            aliases = dict(module_vars)
            TypeCheckingVisitor().update_aliases(module_source, module, aliases, logger)
            names = {
                key: value
                for key, value in aliases.items()
                if key != "__builtins__" and (key not in module_vars or module_vars[key] is not value)
            }
            # the stand-ins are the runtime values, which is what an eager annotation was evaluated with
            stand_ins = {key: module_vars[key] for key in names if key in module_vars}
    except Exception as ex:
        if logger:
            logger.debug(f"Failed to update aliases for TYPE_CHECKING blocks in {module}", exc_info=ex)
    _MODULE_TYPE_CHECKING_CACHE[module] = (names, stand_ins)
    return names, stand_ins


def get_type_checking_stand_ins(obj: Any, logger: logging.Logger | None = None) -> dict:
    """Returns the TYPE_CHECKING stand-ins of the module in which obj is defined."""
    module = getattr(obj, "__module__", None)
    return get_module_type_checking_names(module, logger)[1] if module else {}


def update_module_global_vars(module: str, global_vars: dict, logger: logging.Logger | None) -> None:
    """Adds to global_vars the names of a module, including those of its TYPE_CHECKING blocks."""
    for key, value in vars(import_module(module)).items():  # needed for pydantic-v1
        if key not in global_vars:
            global_vars[key] = value
    global_vars.update(get_module_type_checking_names(module, logger)[0])


def get_global_vars(obj: Any, logger: logging.Logger | None) -> dict:
    global_vars = getattr(obj, "__globals__", {}).copy()
    if is_dataclass(obj):
        next_mro = inspect.getmro(obj)[1]  # type: ignore[arg-type]
        if is_dataclass(next_mro):
            global_vars.update(get_global_vars(next_mro, logger))
    update_module_global_vars(obj.__module__, global_vars, logger)
    _enrich_globals_for_string_forward_refs(global_vars)
    return global_vars


def is_type_like(value: Any) -> bool:
    """Whether a value could be used as a type annotation."""
    from ._optionals import is_alias_type

    return isinstance(value, (type, TypeVar, UnionType)) or hasattr(value, "__origin__") or bool(is_alias_type(value))


def get_owner_class(component: Any) -> type | None:
    """Returns the class in whose body a method is defined, resolved from its qualified name."""
    qualname = getattr(component, "__qualname__", "")
    module = sys.modules.get(getattr(component, "__module__", None))  # type: ignore[arg-type]
    parts = qualname.split(".")[:-1]
    if not parts or "<locals>" in parts or module is None:
        return None
    owner: Any = module
    for part in parts:
        owner = getattr(owner, part, None)
        if owner is None:
            return None
    return owner if inspect.isclass(owner) else None


def get_local_vars(owner: Any) -> dict:
    """Returns the type-like names defined in the body of a class.

    The annotations of a method are evaluated in the scope of the body of the
    class that defines it, so names defined there, e.g. a nested class, must be
    resolvable. Only type-like values are collected, so that unrelated class
    attributes never shadow a module global.
    """
    if not inspect.isclass(owner):  # None when the method has no owner, i.e. a plain function
        return {}
    return {key: value for key, value in vars(owner).items() if is_type_like(value)}


def get_types(obj: Any, logger: logging.Logger | None = None, parent: Any = None) -> dict:
    global_vars = get_global_vars(obj, logger)
    # Locals are only needed for methods. For a class get_type_hints already uses as locals
    # the namespace of each of the bases that the annotations come from.
    local_vars = None if inspect.isclass(obj) else get_local_vars(get_owner_class(obj) or parent)
    try:
        types = get_type_hints(obj, global_vars, local_vars)
    except Exception as ex1:
        types = ex1
    stand_ins = get_type_checking_stand_ins(obj, logger)

    def requires_resolve(typehint) -> bool:
        return type_requires_eval(typehint) or type_uses_stand_in(typehint, stand_ins)

    if not isinstance(types, Exception) and all(not requires_resolve(t) for t in types.values()):
        return types

    try:
        source = textwrap.dedent(inspect.getsource(obj))
        tree = ast.parse(source)
        assert isinstance(tree, ast.Module) and len(tree.body) == 1
        node = tree.body[0]
        assert isinstance(node, (ast.FunctionDef, ast.ClassDef))
    except Exception as ex2:
        if logger:
            logger.debug(f"Failed to parse the source code for {obj}", exc_info=ex2)
        raise type(types)(f"{repr(types)} + {repr(ex2)}") from ex2  # type: ignore[misc,arg-type]

    aliases = __builtins__.copy()  # type: ignore[attr-defined]
    aliases.update(global_vars)
    aliases.update(local_vars or {})
    ex = None
    if isinstance(types, Exception):
        ex = types
        types = {}

    if isinstance(node, ast.ClassDef):
        # dataclass-like, the annotations are the annotated assignments of the class body
        arg_asts = [(n.target.id, n.annotation) for n in node.body if isinstance(n, ast.AnnAssign)]  # type: ignore[union-attr]
    else:
        arg_asts = [(a.arg, a.annotation) for a in node.args.args + node.args.kwonlyargs]

    for name, annotation in arg_asts:
        if annotation and (name not in types or requires_resolve(types[name])):
            try:
                arg_type = get_arg_type(annotation, aliases)
                types[name] = resolve_forward_refs(arg_type, aliases, logger)
            except Exception as ex3:
                types[name] = ex3

    if all(isinstance(t, Exception) for t in types.values()):
        raise ex or next(iter(types.values()))

    return types


def evaluate_postponed_annotations(params, component, parent, logger):
    if not params:
        return
    if is_dataclass(parent) and getattr(component, "__name__", None) == "__init__":
        obj, obj_parent = parent, None
    else:
        obj, obj_parent = component, parent
    if not any(type_requires_eval(p.annotation) for p in params):
        # eagerly evaluated annotations are only wrong if they used a TYPE_CHECKING stand-in
        stand_ins = get_type_checking_stand_ins(obj, logger)
        if not any(type_uses_stand_in(p.annotation, stand_ins) for p in params):
            return
    try:
        types = get_types(obj, logger, obj_parent)
    except Exception as ex:
        logger.debug(f"Unable to evaluate types for {component}", exc_info=ex)
        return
    for param in params:
        if param.name in types:
            param_type = types[param.name]
            if isinstance(param_type, Exception):
                logger.debug(f"Unable to evaluate type of {param.name} from {component}", exc_info=param_type)
                continue
            param.annotation = param_type


def get_return_type(component, logger=None):
    return_type = inspect.signature(component).return_annotation
    if type_requires_eval(return_type):
        global_vars = get_global_vars(component, logger)
        local_vars = get_local_vars(get_owner_class(component))
        try:
            return_type = get_type_hints(component, global_vars, local_vars)["return"]
        except Exception as ex:
            if logger:
                logger.debug(f"Unable to evaluate types for {component}", exc_info=ex)
            return None
    return return_type
