import inspect

import pytest

from jsonargparse import ArgumentError, FromConfigMixin, set_parsing_settings
from jsonargparse._optionals import fsspec_support
from jsonargparse._paths import PathError
from jsonargparse.typing import final, path_type
from jsonargparse_tests.conftest import (
    json_or_yaml_dump,
    skip_if_fsspec_unavailable,
    skip_if_no_pyyaml,
    skip_if_omegaconf_unavailable,
)

if fsspec_support:
    import fsspec

Path_fsr = path_type("fsr")

# __init__ defaults override tests


class DefaultsOverrideParent(FromConfigMixin):
    def __init__(self, parent2: int = 1, parent1: str = "parent_default_value"):
        self.parent1 = parent1
        self.parent2 = parent2


def test_init_defaults_override_subclass(tmp_cwd, subtests):
    config_path = tmp_cwd / "config.yaml"
    config_path.write_text(json_or_yaml_dump({"parent1": "overridden_parent", "child1": "overridden_child"}))

    class DefaultsOverrideChild(DefaultsOverrideParent):
        __from_config_init_defaults__ = config_path

        def __init__(self, child2: int = 2, child1: str = "child_default_value", **kwargs):
            super().__init__(**kwargs)
            self.child1 = child1
            self.child2 = child2

    with subtests.test("overridden subclass defaults"):
        params = inspect.signature(DefaultsOverrideChild.__init__).parameters
        assert params["parent1"].default == "overridden_parent"
        assert params["child1"].default == "overridden_child"

        instance = DefaultsOverrideChild()
        assert instance.parent1 == "overridden_parent"
        assert instance.parent2 == 1
        assert instance.child1 == "overridden_child"
        assert instance.child2 == 2

    with subtests.test("shadow override"):
        instance = DefaultsOverrideChild(child1="shadowed_child", parent1="shadowed_parent", child2=3)
        assert instance.parent1 == "shadowed_parent"
        assert instance.parent2 == 1
        assert instance.child1 == "shadowed_child"
        assert instance.child2 == 3

    with subtests.test("parent class unaffected"):
        params = inspect.signature(DefaultsOverrideParent.__init__).parameters
        assert params["parent1"].default == "parent_default_value"

        parent = DefaultsOverrideParent()
        assert parent.parent1 == "parent_default_value"


def test_init_defaults_override_keyword_only_parameters(tmp_cwd):
    config_path = tmp_cwd / "config.yaml"
    config_path.write_text(json_or_yaml_dump({"parent1": "overridden_parent", "child1": "overridden_child"}))

    class DefaultsOverrideKeywordOnlyParent(FromConfigMixin):
        def __init__(self, *, parent1: str = "parent_default_value", parent2: int = 1):
            self.parent1 = parent1
            self.parent2 = parent2

    class DefaultsOverrideKeywordOnlyChild(DefaultsOverrideKeywordOnlyParent):
        __from_config_init_defaults__ = config_path

        def __init__(self, *, child2: int = 2, child1: str = "child_default_value", **kwargs):
            super().__init__(**kwargs)
            self.child1 = child1
            self.child2 = child2

    params = inspect.signature(DefaultsOverrideKeywordOnlyChild.__init__).parameters
    assert params["parent1"].default == "overridden_parent"
    assert params["child1"].default == "overridden_child"

    instance = DefaultsOverrideKeywordOnlyChild()
    assert instance.parent1 == "overridden_parent"
    assert instance.parent2 == 1
    assert instance.child1 == "overridden_child"
    assert instance.child2 == 2


def test_init_defaults_override_preserve_required(tmp_cwd):
    config_path = tmp_cwd / "config.yaml"
    config_path.write_text(json_or_yaml_dump({"param2": 2}))

    class DefaultsOverrideRequiredParameters(FromConfigMixin):
        __from_config_init_defaults__ = config_path

        def __init__(self, param1: str, param2: int = 1):
            self.param1 = param1
            self.param2 = param2

    with pytest.raises(TypeError, match="missing 1 required positional argument: 'param1'"):
        DefaultsOverrideRequiredParameters()

    instance = DefaultsOverrideRequiredParameters(param1="required")
    assert instance.param1 == "required"
    assert instance.param2 == 2


def test_init_defaults_override_required_not_allowed(tmp_cwd):
    config_path = tmp_cwd / "config.yaml"
    config_path.write_text(json_or_yaml_dump({"param1": 2}))

    with pytest.raises(TypeError, match="Overriding of required parameters not allowed: 'param1'"):

        class DefaultsOverrideRequiredNotAllowed(FromConfigMixin):
            __from_config_init_defaults__ = config_path

            def __init__(self, param1: int):
                self.param1 = param1  # pragma: no cover


def test_init_defaults_override_class_with_init_subclass(tmp_cwd):
    config_path = tmp_cwd / "config.yaml"
    config_path.write_text(json_or_yaml_dump({"parent": "overridden_parent", "child": "overridden_child"}))

    class DefaultsOverrideBase(FromConfigMixin):
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            cls.original_init_subclass_ran = True

        def __init__(self, parent: str = "default_value"):
            self.parent = parent

    class DefaultsOverrideDerived(DefaultsOverrideBase):
        __from_config_init_defaults__ = config_path

        def __init__(self, child: str = "default_value", **kwargs):
            super().__init__(**kwargs)
            self.child = child

    params = inspect.signature(DefaultsOverrideDerived.__init__).parameters
    assert params["parent"].default == "overridden_parent"
    assert params["child"].default == "overridden_child"

    instance = DefaultsOverrideDerived()
    assert instance.parent == "overridden_parent"
    assert instance.child == "overridden_child"
    assert instance.original_init_subclass_ran


@skip_if_omegaconf_unavailable
def test_init_defaults_override_parser_kwargs(tmp_cwd):
    config_path = tmp_cwd / "config.yaml"
    config_path.write_text(json_or_yaml_dump({"param1": "there", "param2": "hi ${.param1}"}))

    class DefaultsOverrideParserKwargs(FromConfigMixin):
        __from_config_init_defaults__ = config_path
        __from_config_parser_kwargs__ = {"parser_mode": "omegaconf+"}

        def __init__(self, param1: str = "", param2: str = ""):
            self.param1 = param1
            self.param2 = param2

    instance = DefaultsOverrideParserKwargs()
    assert instance.param1 == "there"
    assert instance.param2 == "hi there"


def test_init_defaults_override_file_not_found():
    class DefaultsOverrideFileNotFound(DefaultsOverrideParent):
        __from_config_init_defaults__ = "non_existent_file.yaml"

    instance = DefaultsOverrideFileNotFound()
    assert instance.parent1 == "parent_default_value"
    assert instance.parent2 == 1


def test_init_defaults_override_invalid():
    with pytest.raises(TypeError, match="__from_config_init_defaults__ must be str, PathLike, or None"):

        class DefaultsOverrideInvalid(DefaultsOverrideParent):
            __from_config_init_defaults__ = 123  # Invalid type


# from_config method tests


class FromConfigMethodParent(FromConfigMixin):
    def __init__(self, parent_param: str = "parent_default"):
        self.parent_param = parent_param


class FromConfigMethodChild(FromConfigMethodParent):
    def __init__(self, child_param: str = "child_default", **kwargs):
        super().__init__(**kwargs)
        self.child_param = child_param


def test_from_config_method_path(tmp_cwd):
    config_path = tmp_cwd / "config.yaml"
    config_path.write_text(json_or_yaml_dump({"parent_param": "value_from_file"}))

    instance = FromConfigMethodParent.from_config(config_path)
    assert instance.parent_param == "value_from_file"


@skip_if_fsspec_unavailable
def test_from_config_method_path_fsspec_relative_paths():
    class FromConfigMethodFsspecRelativePath(FromConfigMixin):
        def __init__(self, file: Path_fsr):
            self.file = file

    config_path = "memory://from_config/config.yaml"
    file_path = "memory://from_config/file.txt"
    with fsspec.open(config_path, "w") as f:
        f.write(json_or_yaml_dump({"file": "file.txt"}))
    with fsspec.open(file_path, "w") as f:
        f.write("value_from_fsspec")

    set_parsing_settings(config_read_mode_fsspec_enabled=True)
    try:
        instance = FromConfigMethodFsspecRelativePath.from_config(config_path)
    finally:
        set_parsing_settings(config_read_mode_fsspec_enabled=False)

    assert instance.file.absolute == file_path
    assert instance.file.read_text() == "value_from_fsspec"


def test_from_config_method_path_does_not_exist(tmp_cwd):
    config_path = tmp_cwd / "config.yaml"

    with pytest.raises(PathError, match="File does not exist:"):
        FromConfigMethodParent.from_config(config_path)


@skip_if_no_pyyaml
def test_from_config_method_path_invalid_yaml(tmp_cwd):
    config_path = tmp_cwd / "config.yaml"
    config_path.write_text("::: invalid content :::")

    with pytest.raises(ArgumentError, match="Invalid content in sub-config file"):
        FromConfigMethodParent.from_config(config_path)


def test_from_config_method_path_not_dict(tmp_cwd):
    config_path = tmp_cwd / "config.yaml"
    config_path.write_text("[1, 2]")

    with pytest.raises(ArgumentError, match=r"Not a valid subclass of FromConfigMethodParent. Got value: \[1, 2\]"):
        FromConfigMethodParent.from_config(config_path)


def test_from_config_method_dict():
    class FromConfigMethodDict(FromConfigMixin):
        def __init__(self, param: str = "default_value"):
            self.param = param

    instance = FromConfigMethodDict.from_config({"param": "value_from_dict"})
    assert instance.param == "value_from_dict"


def test_from_config_method_positional_only_and_var_positional():
    class FromConfigMethodPositionals(FromConfigMixin):
        def __init__(self, first: int, /, *rest: int, param: str = "default_value"):
            self.first = first
            self.rest = rest
            self.param = param

    instance = FromConfigMethodPositionals.from_config({"first": 1, "rest": [2, 3]})
    assert (instance.first, instance.rest, instance.param) == (1, (2, 3), "default_value")


def test_from_config_method_default():
    from os import PathLike
    from typing import Literal, Type, TypeVar, Union

    T = TypeVar("T")
    default_config = {"param1": "method_default_value"}

    class FromConfigMethodDefault(FromConfigMixin):
        @classmethod
        def from_config(cls: Type[T], config: Union[str, PathLike, dict, Literal["default"]] = "default") -> T:
            if config == "default":
                config = default_config
            return super().from_config(config)

        def __init__(self, param1: str = "default_value", param2: int = 1):
            self.param1 = param1
            self.param2 = param2

    instance = FromConfigMethodDefault.from_config()
    assert instance.param1 == "method_default_value"
    assert instance.param2 == 1


def test_from_config_method_subclass():
    instance = FromConfigMethodChild.from_config(
        {"parent_param": "overridden_parent", "child_param": "overridden_child"}
    )
    assert isinstance(instance, FromConfigMethodChild)
    assert instance.parent_param == "overridden_parent"
    assert instance.child_param == "overridden_child"


def test_from_config_method_class_path_subclass():
    instance = FromConfigMethodParent.from_config(
        {
            "class_path": f"{__name__}.FromConfigMethodChild",
            "init_args": {"parent_param": "overridden_parent", "child_param": "overridden_child"},
        }
    )
    assert isinstance(instance, FromConfigMethodChild)
    assert instance.parent_param == "overridden_parent"
    assert instance.child_param == "overridden_child"


def test_from_config_method_subclasses_disabled(tmp_cwd):
    @final
    class FromConfigMethodFinal(FromConfigMixin):
        def __init__(self, param: int = 1):
            self.param = param

    config_path = tmp_cwd / "config.yaml"
    config_path.write_text(json_or_yaml_dump({"param": 2}))
    instance = FromConfigMethodFinal.from_config(config_path)
    assert instance.param == 2
    with pytest.raises(ArgumentError, match="Subclasses are disabled for FromConfigMethodFinal"):
        FromConfigMethodFinal.from_config({"class_path": "Other"})


class SomeOtherClass:
    pass


def test_from_config_method_class_path_not_subclass():
    with pytest.raises(ArgumentError, match="SomeOtherClass does not correspond to a subclass of"):
        FromConfigMethodParent.from_config({"class_path": f"{__name__}.SomeOtherClass"})


@skip_if_omegaconf_unavailable
def test_from_config_method_parser_kwargs():
    class FromConfigMethodParserKwargs(FromConfigMixin):
        __from_config_parser_kwargs__ = {"parser_mode": "omegaconf+"}

        def __init__(self, param1: str, param2: str):
            self.param1 = param1
            self.param2 = param2

    instance = FromConfigMethodParserKwargs.from_config({"param1": "there", "param2": "hi ${.param1}"})
    assert instance.param1 == "there"
    assert instance.param2 == "hi there"


def test_from_config_method_partial_config_with_required_parameter():
    class FromConfigMethodPartial(FromConfigMixin):
        def __init__(self, required_param: str, optional_param: str = "default_value"):  # pragma: no cover
            self.required_param = required_param
            self.optional_param = optional_param

    with pytest.raises(ArgumentError, match="the following arguments are required: required_param"):
        FromConfigMethodPartial.from_config({"optional_param": "from_config"})
