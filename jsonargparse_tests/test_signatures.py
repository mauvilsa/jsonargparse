from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar, Union
from unittest.mock import patch

import pytest

from jsonargparse import (
    ActionParser,
    ArgumentError,
    Namespace,
    add_instantiator,
    lazy_instance,
)
from jsonargparse._optionals import docstring_parser_support
from jsonargparse._subcommands import find_action
from jsonargparse_tests.conftest import (
    capture_logs,
    get_parse_args_stdout,
    get_parser_help,
    json_or_yaml_dump,
    json_or_yaml_load,
    skip_if_docstring_parser_unavailable,
)

# add_class_arguments tests


class Class0:
    def __init__(self, c0_a0: Optional[str] = "0"):
        pass


class Class1(Class0):
    def __init__(self, c1_a1: str, c1_a2: Any = 2.0, c1_a3=None, c1_a4: int = 4, c1_a5: str = "5"):
        """Class1 short description

        Args:
            c1_a2: c1_a2 description
            c1_a3: c1_a3 description
        """
        super().__init__()
        self.c1_a1 = c1_a1

    def __call__(self):
        return self.c1_a1


class Class2(Class1):
    def __init__(self, c2_a0, c3_a4, *args, **kwargs):
        super().__init__(c3_a4, *args, **kwargs)


class Class3(Class2):
    def __init__(
        self,
        c3_a0: Any,
        c3_a1="1",
        c3_a2: float = 2.0,
        c3_a3: bool = False,
        c3_a4: Optional[str] = None,
        c3_a5: Union[int, float, str, List[int], Dict[str, float]] = 5,
        c3_a6: Optional[Class1] = None,
        c3_a7: Tuple[str, int, float] = ("7", 7, 7.0),
        c3_a8: Optional[Tuple[str, Class1]] = None,
        c1_a5: str = "five",
        **kwargs,
    ):
        """Class3 short description

        Args:
            c3_a0: c3_a0 description
            c3_a1: c3_a1 description
            c3_a2: c3_a2 description
            c3_a4: c3_a4 description
            c3_a5: c3_a5 description
        """
        super().__init__(None, c3_a4, **kwargs)


def test_add_class_failure_not_a_class(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_class_arguments("Not a class")
    ctx.match("Expected 'class_type' parameter to be a class")


def test_add_class_failure_positional_without_type(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_class_arguments(Class2)
    ctx.match(f"Parameter 'c2_a0' from '{__name__}.Class2.__init__' does not specify a type")


def test_add_class_without_nesting(parser):
    parser.add_class_arguments(Class3)

    assert "Class3" in parser.groups
    for key in "c3_a0 c3_a1 c3_a2 c3_a3 c3_a4 c3_a5 c3_a6 c3_a7 c3_a8 c1_a2 c1_a3 c1_a4 c1_a5".split():
        assert find_action(parser, key) is not None, f"{key} should be in parser but is not"
    for key in ["c2_a0", "c1_a1", "c0_a0"]:
        assert find_action(parser, key) is None, f"{key} should not be in parser but is"

    cfg = parser.parse_args(["--c3_a0=0", "--c3_a3=true", "--c3_a4=a"]).clone(with_meta=False)
    assert cfg.as_dict() == {
        "c1_a2": 2.0,
        "c1_a3": None,
        "c1_a4": 4,
        "c1_a5": "five",
        "c3_a0": 0,
        "c3_a1": "1",
        "c3_a2": 2.0,
        "c3_a3": True,
        "c3_a4": "a",
        "c3_a5": 5,
        "c3_a6": None,
        "c3_a7": ("7", 7, 7.0),
        "c3_a8": None,
    }
    assert [1, 2] == parser.parse_args(["--c3_a0=0", "--c3_a5=[1,2]"]).c3_a5
    assert {"k": 5.0} == parser.parse_args(["--c3_a0=0", '--c3_a5={"k": 5.0}']).c3_a5
    assert ("3", 3, 3.0) == parser.parse_args(["--c3_a0=0", '--c3_a7=["3", 3, 3.0]']).c3_a7
    assert "a" == Class3(**cfg.as_dict())()

    with pytest.raises(ArgumentError, match="the following arguments are required: c3_a0"):
        parser.parse_args([])

    if docstring_parser_support:
        assert "Class3 short description" == parser.groups["Class3"].title
        for key in ["c3_a0", "c3_a1", "c3_a2", "c3_a4", "c3_a5", "c1_a2"]:
            assert f"{key} description" == find_action(parser, key).help
        for key in ["c3_a3", "c3_a7", "c1_a4"]:
            assert f"{key} description" != find_action(parser, key).help


def test_add_class_nested_as_group_false(parser):
    added_args = parser.add_class_arguments(Class3, "g", as_group=False)

    assert "g" not in parser.groups
    assert 13 == len(added_args)
    assert all(a.startswith("g.") for a in added_args)

    for key in "c3_a0 c3_a1 c3_a2 c3_a3 c3_a4 c3_a5 c3_a6 c3_a7 c3_a8 c1_a2 c1_a3 c1_a4 c1_a5".split():
        assert find_action(parser, f"g.{key}") is not None, f"{key} should be in parser but is not"
    for key in ["c2_a0", "c1_a1", "c0_a0"]:
        assert find_action(parser, f"g.{key}") is None, f"{key} should not be in parser but is"

    defaults = parser.get_defaults()
    assert defaults == parser.instantiate(defaults)


def test_add_class_default_group_title(parser):
    parser.add_class_arguments(Class0)
    assert str(Class0) == parser.groups["Class0"].title


class WithDefault:
    def __init__(self, p1: int = 1, p2: str = "-"):
        pass  # pragma: no cover


def test_add_class_with_default(parser):
    parser.add_class_arguments(WithDefault, "cls", default=lazy_instance(WithDefault, p1=2))
    defaults = parser.get_defaults()
    assert defaults == Namespace(cls=Namespace(p1=2, p2="-"))


def test_add_class_env_help(parser):
    parser.env_prefix = "APP"
    parser.default_env = True
    parser.add_class_arguments(WithDefault, "cls")
    help_str = get_parser_help(parser)
    assert "ARG:   --cls CONFIG" in help_str
    assert "ARG:   --cls.p1 P1" in help_str
    assert "ENV:   APP_CLS\n" in help_str
    assert "ENV:   APP_CLS__P1" in help_str


class NoParams:
    pass


def test_add_class_without_parameters(parser):
    parser.add_argument("--cfg", action="config")
    parser.add_class_arguments(NoParams, "no_params")

    help_str = get_parser_help(parser)
    assert "no_params" not in help_str

    cfg = parser.parse_args([])
    assert "no_params" not in cfg
    init = parser.instantiate(cfg)
    assert isinstance(init.no_params, NoParams)

    config = {"no_params": {"class_path": f"{__name__}.NoParams"}}
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args([f"--cfg={json.dumps(config)}"])
    ctx.match("Group 'no_params' does not accept option 'class_path'")


class NestedWithParams:
    def __init__(self, p1: int):
        self.p1 = p1


class NestedWithoutParams:
    pass


def test_add_class_nested_with_and_without_parameters(parser):
    parser.add_class_arguments(NestedWithParams, "group.first")
    parser.add_class_arguments(NestedWithoutParams, "group.second")

    cfg = parser.parse_args(["--group.first.p1=2"])
    assert cfg.group.first == Namespace(p1=2)
    assert "group.second" not in cfg
    init = parser.instantiate(cfg)
    assert isinstance(init.group.first, NestedWithParams)
    assert isinstance(init.group.second, NestedWithoutParams)


class SkippedUnderscoreParam:
    def __init__(self, _a0=None):
        pass  # pragma: no cover


def test_add_class_skipped_underscore_parameter(parser):
    assert [] == parser.add_class_arguments(SkippedUnderscoreParam)


class WithNew:
    def __new__(cls, a1: int = 1, a2: float = 2.3):  # pragma: no cover
        obj = object.__new__(cls)
        obj.a1 = a1  # type: ignore[attr-defined]
        obj.a2 = a2  # type: ignore[attr-defined]
        return obj


def test_add_class_implemented_with_new(parser):
    parser.add_class_arguments(WithNew, "a")
    cfg = parser.parse_args(["--a.a1=4"])
    assert cfg.a == Namespace(a1=4, a2=2.3)


class RequiredParams:
    def __init__(self, n: int, m: float):
        self.n = n
        self.m = m


def test_add_class_group_name_dash_required_parameters(parser):
    parser.add_class_arguments(RequiredParams, "required-params")
    assert "required-params" in parser.groups
    cfg = parser.parse_args(["--required-params.n=6", "--required-params.m=0.9"])
    init = parser.instantiate(cfg)
    assert isinstance(init.required_params, RequiredParams)
    assert init.required_params.n == 6
    assert init.required_params.m == 0.9


def test_add_class_with_required_parameters(parser):
    parser.add_class_arguments(RequiredParams, "model")
    parser.add_argument("--config", action="config")

    for args in [
        [],
        ["--model.n=2"],
        ["--model.m=0.1"],
        ["--model.n=x", "--model.m=0.1"],
    ]:
        pytest.raises(ArgumentError, lambda: parser.parse_args(args))

    out = get_parse_args_stdout(parser, ["--model.m=0.1", "--print_config"])
    assert json_or_yaml_load(out) == {"model": {"n": None, "m": 0.1}}

    cfg = parser.parse_args([f"--config={out}", "--model.n=3"])
    assert cfg.model == Namespace(m=0.1, n=3)


def test_add_class_conditional_kwargs(parser):
    from jsonargparse_tests.test_parameter_resolvers import ClassG

    parser.add_class_arguments(ClassG, "g")

    cfg = parser.get_defaults()
    assert cfg.g == Namespace(func=None, kmg1=1)

    cfg = parser.parse_args(["--g.func=1", "--g.kmg2=x"])
    assert cfg.g == Namespace(func="1", kmg1=1, kmg2="x")
    init = parser.instantiate(cfg)
    init.g._run()
    assert init.g.called == "method1"

    cfg = parser.parse_args(["--g.func=2", "--g.kmg4=5"])
    assert cfg.g == Namespace(func="2", kmg1=1, kmg4=5)
    init = parser.instantiate(cfg)
    init.g._run()
    assert init.g.called == "method2"

    help_str = get_parser_help(parser)
    module = "jsonargparse_tests.test_parameter_resolvers"
    expected = [
        f"origins: {module}.ClassG._run:3; {module}.ClassG._run:5",
        f"origins: {module}.ClassG._run:5",
    ]
    if docstring_parser_support:
        expected += [
            "help for func (required, type: str)",
            "help for kmg1 (type: int, default: 1)",
            "help for kmg3 (type: bool, default: Conditional<ast-resolver> {True, False})",
            "help for kmg4 (type: int, default: Conditional<ast-resolver> {4, NOT_ACCEPTED})",
        ]
        if sys.version_info < (3, 14):
            expected += [
                "help for kmg2 (type: Union[str, float], default: Conditional<ast-resolver> {-, 2.3})",
            ]
        else:
            expected += [
                "help for kmg2 (type: str | float, default: Conditional<ast-resolver> {-, 2.3})",
            ]
    for value in expected:
        assert value in help_str


class Debug1:
    def __init__(self, c1_a1: float, c1_a2: int = 1):
        pass  # pragma: no cover


class Debug2(Debug1):
    def __init__(self, *args, c2_a1: int = 2, c2_a2: float = 0.2, **kwargs):
        pass  # pragma: no cover


def test_add_class_skip_parameter_debug_logging(parser, logger):
    parser.logger = logger
    with capture_logs(logger) as logs:
        parser.add_class_arguments(Debug2, skip={"c2_a2"})
    assert 1 == len(logs.getvalue().strip().split("\n"))
    assert 'Skipping parameter "c2_a2"' in logs.getvalue()
    assert "because of: Parameter requested to be skipped" in logs.getvalue()


class WithinSubcommand:
    def __init__(self, a: int = 1):
        self.a = a


def test_add_class_in_subcommand(parser, subparser):
    subcommands = parser.add_subcommands()
    subparser.add_class_arguments(WithinSubcommand, "class")
    subcommands.add_subcommand("cmd", subparser)

    cfg = parser.parse_args(["cmd"])
    assert cfg.subcommand == "cmd"
    init = parser.instantiate(cfg)
    assert isinstance(init["cmd"]["class"], WithinSubcommand)
    assert init["cmd"]["class"].a == 1


def test_add_class_group_config(parser, tmp_cwd):
    parser.add_class_arguments(Class0, "a")
    path = Path("a.yaml")
    path.write_text(json_or_yaml_dump({"c0_a0": "x"}))
    cfg = parser.parse_args(["--a=a.yaml"])
    assert str(cfg.a.pop("__path__")) == str(path)
    assert cfg.a == Namespace(c0_a0="x")


def test_add_class_group_config_not_found(parser, tmp_cwd):
    parser.add_class_arguments(Class0, "a")
    with pytest.raises(ArgumentError, match="Unable to load config .does_not_exist.yaml"):
        parser.parse_args(["--a=does_not_exist.yaml"])


class WithDocstring:
    def __init__(self, a1: int = 1):
        """
        Args:
            a1: a1 description
        """


@skip_if_docstring_parser_unavailable
def test_add_class_docstring_parse_fail(parser, logger):
    from docstring_parser import ParseError

    parser.logger = logger
    with capture_logs(logger) as logs:
        with patch("docstring_parser.parse", side_effect=ParseError):
            parser.add_class_arguments(WithDocstring)

    assert "Failed parsing docstring" in logs.getvalue()
    help_str = get_parser_help(parser)
    assert "--a1 A1" in help_str
    assert "a1 description" not in help_str


def test_add_class_custom_instantiator(parser, clear_instantiators):
    def instantiate(cls, **kwargs):
        instance = cls(**kwargs)
        instance.call = "custom"
        return instance

    parser.add_class_arguments(Class0, "a")
    add_instantiator(instantiate, Class0)
    cfg = parser.parse_args([])
    init = parser.instantiate(cfg)
    assert isinstance(init.a, Class0)
    assert init.a.call == "custom"


X = TypeVar("X")
Y = TypeVar("Y")


class WithGenerics(Generic[X, Y]):
    def __init__(self, a: X, b: Y):  # pragma: no cover
        self.a = a
        self.b = b


def test_add_class_generics(parser):
    parser.add_class_arguments(WithGenerics[int, complex], "p")
    cfg = parser.parse_args(["--p.a=5", "--p.b=(6+7j)"])
    assert cfg.p == Namespace(a=5, b=6 + 7j)


class UnmatchedDefaultType:
    def __init__(self, p1: str, p2: bool = "deprecated"):  # type: ignore[assignment]
        self.p2 = p2


def test_add_class_unmatched_default_type(parser):
    parser.add_class_arguments(UnmatchedDefaultType, "cls")
    cfg = parser.parse_args(["--cls.p1=x"])
    assert cfg.cls == Namespace(p1="x", p2="deprecated")
    init = parser.instantiate(cfg)
    assert init.cls.p2 == "deprecated"
    dump = parser.dump(cfg)
    assert json_or_yaml_load(dump) == {"cls": {"p1": "x", "p2": "deprecated"}}


class LeafClass:
    def __init__(self, p1: int = 1, p2: str = "-"):
        self.p1 = p1
        self.p2 = p2


def test_add_class_and_action_parser(parser, subparser):
    subparser.add_class_arguments(LeafClass, "deep.leaf")
    parser.add_argument("--nested", action=ActionParser(parser=subparser))
    parser.add_argument("--config", action="config")

    config = {
        "nested": {
            "deep": {
                "leaf": {
                    "p1": 2,
                    "p2": "x",
                }
            }
        }
    }
    cfg = parser.parse_args([f"--config={json.dumps(config)}"])
    init = parser.instantiate(cfg)
    assert list(cfg.keys()) == ["nested.deep.leaf.p1", "nested.deep.leaf.p2", "config"]
    assert list(init.keys()) == ["nested.deep.leaf", "config"]
    assert isinstance(init.nested.deep.leaf, LeafClass)
    assert init.nested.deep.leaf.p1 == 2
    assert init.nested.deep.leaf.p2 == "x"


# add_method_arguments tests


class WithMethods:
    def normal_method(self, a1="1", a2: float = 2.0, a3: bool = False):
        """normal_method short description

        Args:
            a1: a1 description
            a2: a2 description
        """
        return a1

    @staticmethod
    def static_method(a1: str, a2: float = 2.0, _a3=None):
        return a1


def test_add_method_failure_adding(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_method_arguments("WithMethods", "normal_method")
    ctx.match('Expected "class_type" argument to be a class')
    with pytest.raises(ValueError) as ctx:
        parser.add_method_arguments(WithMethods, "does_not_exist")
    ctx.match('Expected "method_name" argument to be a callable member')


def test_add_method_normal_and_static(parser):
    added_args1 = parser.add_method_arguments(WithMethods, "normal_method", "m")
    added_args2 = parser.add_method_arguments(WithMethods, "static_method", "s")

    assert "m" in parser.groups
    assert "s" in parser.groups
    assert added_args1 == ["m.a1", "m.a2", "m.a3"]
    assert added_args2 == ["s.a1", "s.a2"]

    for key in ["m.a1", "m.a2", "m.a3", "s.a1", "s.a2"]:
        assert find_action(parser, key) is not None, f"{key} should be in parser but is not"
    assert find_action(parser, "s._a3") is None, "s._a3 should not be in parser but is"

    cfg = parser.parse_args(["--m.a1=x", "--s.a1=y"]).clone(with_meta=False).as_dict()
    assert cfg == {"m": {"a1": "x", "a2": 2.0, "a3": False}, "s": {"a1": "y", "a2": 2.0}}
    assert "x" == WithMethods().normal_method(**cfg["m"])
    assert "y" == WithMethods.static_method(**cfg["s"])

    if docstring_parser_support:
        assert "normal_method short description" == parser.groups["m"].title
        assert str(WithMethods.static_method) == parser.groups["s"].title
        for key in ["m.a1", "m.a2"]:
            assert f"{key.split('.')[1]} description" == find_action(parser, key).help
        for key in ["m.a3", "s.a1", "s.a2"]:
            assert f"{key.split('.')[1]} description" != find_action(parser, key).help


class SubWithMethod(WithMethods):
    def normal_method(self, *args, p2: int = 2, **kwargs):  # pragma: no cover
        p1 = super().normal_method(**kwargs)
        return p1, p2


def test_add_method_parent_classes(parser):
    added_args = parser.add_method_arguments(SubWithMethod, "normal_method", "m")
    assert "m" in parser.groups
    assert added_args == ["m.p2", "m.a1", "m.a2", "m.a3"]


class Model:
    pass


class TrainerLike:
    def foo(self, model: Model, x: int, y: float = 1.0):
        """Sample extra function.

        Args:
            model: A model
            x: The x
            y: The y
        """


@skip_if_docstring_parser_unavailable
def test_add_method_required_argument_in_parse_args_help(parser):
    parser.add_method_arguments(TrainerLike, "foo", skip={"model"})

    help_str = get_parse_args_stdout(parser, ["--help"])
    assert "The x (required, type: int)" in help_str
    assert "The y (type: float, default: 1.0)" in help_str


@skip_if_docstring_parser_unavailable
def test_add_method_required_argument_in_subcommand_parse_args_help(parser, subparser):
    subparser.description = "Sample extra function:"
    subparser.add_method_arguments(TrainerLike, "foo", skip={"model"})
    parser.add_subcommands().add_subcommand("foo", subparser)

    help_str = get_parse_args_stdout(parser, ["foo", "--help"])
    assert "The x (required, type: int)" in help_str
    assert "The y (type: float, default: 1.0)" in help_str


# add_function_arguments tests


def test_add_function_failure_not_callable(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_function_arguments("not callable")
    ctx.match('Expected "function" argument to be a callable')


def func(a1="1", a2: float = 2.0, a3: bool = False, a4=None):
    """func short description

    Args:
        a1: a1 description
        a2: a2 description
        a4: a4 description
    """
    return a1


def test_add_function_arguments(parser):
    parser.add_function_arguments(func)

    assert "func" in parser.groups

    for key in ["a1", "a2", "a3", "a4"]:
        assert find_action(parser, key) is not None, f"{key} should be in parser but is not"

    cfg = parser.parse_args(["--a1=x"]).clone(with_meta=False).as_dict()
    assert cfg == {"a1": "x", "a2": 2.0, "a3": False, "a4": None}
    assert "x" == func(**cfg)

    if docstring_parser_support:
        assert "func short description" == parser.groups["func"].title
        for key in ["a1", "a2", "a4"]:
            assert f"{key} description" == find_action(parser, key).help


def func_skip_params(a1="1", a2: float = 2.0, a3: bool = False, a4: int = 4):
    return a1  # pragma: no cover


def test_add_function_skip_names(parser):
    added_args = parser.add_function_arguments(func_skip_params, skip={"a2", "a4"})
    assert added_args == ["a1", "a3"]


def test_add_function_skip_positional_and_name(parser):
    added_args = parser.add_function_arguments(func_skip_params, skip={1, "a3"})
    assert added_args == ["a2", "a4"]


def test_add_function_skip_positionals_invalid(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_function_arguments(func_skip_params, skip={1, 2})
    ctx.match("Unexpected number of positionals to skip")


def func_invalid_type(a1: None):
    return a1  # pragma: no cover


def test_add_function_invalid_type(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_function_arguments(func_invalid_type)
    ctx.match("all mandatory parameters must have a supported type")


def func_implicit_optional(a1: int = None):  # type: ignore[assignment]
    return a1  # pragma: no cover


def test_add_function_implicit_optional(parser):
    parser.add_function_arguments(func_implicit_optional)
    assert None is parser.parse_args(["--a1=null"]).a1


def func_type_as_string(a2: "int"):
    return a2  # pragma: no cover


def test_add_function_fail_untyped_true_str_type(parser):
    added_args = parser.add_function_arguments(func_type_as_string, fail_untyped=True)
    assert ["a2"] == added_args


def func_untyped_params(a1, a2=None):
    return a1  # pragma: no cover


def test_add_function_fail_untyped_true_untyped_params(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_function_arguments(func_untyped_params, fail_untyped=True)
    ctx.match("Parameter 'a1' from .* does not specify a type")


def test_add_function_fail_untyped_false(parser):
    added_args = parser.add_function_arguments(func_untyped_params, fail_untyped=False)
    assert ["a1", "a2"] == added_args
    assert parser.parse_args(["--a1=x"]) == Namespace(a1="x", a2=None)
    with pytest.raises(ArgumentError, match="the following arguments are required: a1"):
        parser.parse_args([])


def func_untyped_optional(a1: int, a2=None):
    return a1  # pragma: no cover


def test_add_function_fail_untyped_true_untyped_optional(parser):
    added_args = parser.add_function_arguments(func_untyped_optional, fail_untyped=True)
    assert ["a1", "a2"] == added_args
    assert parser.parse_args(["--a1=123"]) == Namespace(a1=123, a2=None)
    with pytest.raises(ArgumentError, match="Expected a .*int.* Got value: x"):
        parser.parse_args(["--a1=x"])


def test_add_function_group_config(parser, tmp_cwd):
    parser.add_function_arguments(func, "func")

    cfg_path = Path("config.yaml")
    cfg_path.write_text(json_or_yaml_dump({"a1": "one", "a3": True}))

    cfg = parser.parse_args([f"--func={cfg_path}"]).clone(with_meta=False)
    assert cfg.func == Namespace(a1="one", a2=2.0, a3=True, a4=None)

    cfg = parser.parse_args(['--func={"a1": "ONE"}']).clone(with_meta=False)
    assert cfg.func == Namespace(a1="ONE", a2=2.0, a3=False, a4=None)

    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--func="""'])
    ctx.match("Unable to load config")


def test_add_function_group_config_within_config(parser, tmp_cwd):
    parser.add_argument("--cfg", action="config")
    parser.add_function_arguments(func, "func")

    cfg_path = Path("subdir", "config.yaml")
    subcfg_path = Path("subsubdir", "func_config.yaml")
    Path("subdir", "subsubdir").mkdir(parents=True)
    cfg_path.write_text(json_or_yaml_dump({"func": str(subcfg_path)}))
    (cfg_path.parent / subcfg_path).write_text(json_or_yaml_dump({"a1": "one", "a3": True}))

    cfg = parser.parse_args([f"--cfg={cfg_path}"])
    assert str(cfg.func.__path__) == str(subcfg_path)
    assert cfg.func.clone(with_meta=False) == Namespace(a1="one", a2=2.0, a3=True, a4=None)


def func_param_conflict(p1: int, cfg: dict):
    pass  # pragma: no cover


def test_add_function_param_conflict(parser):
    parser.add_argument("--cfg", action="config")
    with pytest.raises(ValueError) as ctx:
        parser.add_function_arguments(func_param_conflict)
    ctx.match("Unable to add parameter 'cfg' from")


def func_positional_and_keyword_only(a: int, /, b: int, *, c: int, d: int = 1):
    pass  # pragma: no cover


def test_add_function_positional_and_keyword_only_parameters(parser):
    parser.add_function_arguments(func_positional_and_keyword_only, as_positional=True)

    # Test that we can parse with both parameters
    cfg = parser.parse_args(["1", "2", "--c=3", "--d=4"])
    assert cfg == Namespace(a=1, b=2, c=3, d=4)
    with pytest.raises(ArgumentError, match="unrecognized arguments: --b=2"):
        parser.parse_args(["1", "--b=2", "--c=3", "--d=4"])
    with pytest.raises(ArgumentError, match="the following arguments are required: c"):
        parser.parse_args(["1", "2", "--d=4"])
