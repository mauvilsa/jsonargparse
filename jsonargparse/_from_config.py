import inspect
from functools import wraps
from os import PathLike
from pathlib import Path
from typing import TypeVar

from ._core import ArgumentParser
from ._optionals import _get_config_read_mode
from ._paths import Path as ConfigPath
from ._required import clear_required, iter_required_keys

__all__ = ["FromConfigMixin"]

T = TypeVar("T")
OVERRIDE_KINDS = {inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}


class FromConfigMixin:
    """Mixin class that adds from config support to classes.

    This mixin does two things:

        1. Adds support for overriding ``__init__`` defaults by defining a
           ``__from_config_init_defaults__`` class attribute pointing to a
           config file path. The overriding of defaults happens on subclass
           creation time. Inspecting the signature will give the overridden
           defaults.

        2. Adds a ``from_config`` ``@classmethod``, that instantiates the class
           based on a config file or dict. If
           ``config_read_mode_fsspec_enabled=True`` is set, then config paths
           can be URLs.

    Attributes:
        __from_config_init_defaults__: Optional path to a config file for
            overriding ``__init__`` defaults.
        __from_config_parser_kwargs__: Additional kwargs to pass to the
            ArgumentParser used for parsing configs.
    """

    __from_config_init_defaults__: str | PathLike | None = None
    __from_config_parser_kwargs__: dict = {}

    def __init_subclass__(cls, **kwargs) -> None:
        """Override ``__init__`` defaults for the subclass based on a config file."""
        super().__init_subclass__(**kwargs)
        _override_init_defaults(cls, cls.__from_config_parser_kwargs__)

    @classmethod
    def from_config(cls: type[T], config: str | PathLike | dict) -> T:
        """Instantiate current class based on a config file or dict.

        Args:
            config: Path to a config file or a dict with config values.
        """
        parser = ArgumentParser(exit_on_error=False, **cls.__from_config_parser_kwargs__)  # type: ignore[attr-defined]
        parser.add_argument("--from_config", type=cls, required=True, sub_configs=True)
        return _parse_and_instantiate(parser, config)


def _parse_and_instantiate(parser: ArgumentParser, config: str | PathLike | dict):
    """Parses a config as the value of the ``from_config`` key of ``parser``, and instantiates it."""
    if not isinstance(config, dict):
        config = str(ConfigPath(config, mode=_get_config_read_mode()))  # else a subclass type takes it as a class path
    cfg = parser.parse_object({"from_config": config}, defaults=False)
    return parser.instantiate(cfg).from_config


def _override_init_defaults(cls: type[T], parser_kwargs: dict) -> None:
    """Override ``__init__`` defaults for ``cls`` based on ``__from_config_init_defaults__``."""
    config = getattr(cls, "__from_config_init_defaults__", None)
    if not isinstance(config, (str, PathLike, type(None))):
        raise TypeError("__from_config_init_defaults__ must be str, PathLike, or None")
    if not (isinstance(config, (str, PathLike)) and Path(config).is_file()):
        return

    parser = ArgumentParser(exit_on_error=False, **parser_kwargs)
    parser.add_class_arguments(cls, "from_config", instantiate=False)
    for required in iter_required_keys(parser):
        clear_required(parser, required)
    defaults = _parse_and_instantiate(parser, config).as_dict()
    _override_init_defaults_this_class(cls, defaults)
    _override_init_defaults_parent_classes(cls, defaults)


def _override_init_defaults_this_class(cls: type[T], defaults: dict) -> None:
    params = inspect.signature(cls.__init__).parameters
    for name, default in defaults.copy().items():
        param = params.get(name)
        if param and param.kind in OVERRIDE_KINDS:
            if param.default == inspect._empty:
                raise TypeError(f"Overriding of required parameters not allowed: '{param.name}'")
            defaults.pop(name)
            if param.kind == inspect.Parameter.KEYWORD_ONLY:
                cls.__init__.__kwdefaults__[name] = default  # type: ignore[index]
            else:
                required = [p for p in params.values() if p.kind in OVERRIDE_KINDS and p.default == inspect._empty]
                index = list(params).index(name) - len(required)
                aux = cls.__init__.__defaults__ or ()
                cls.__init__.__defaults__ = aux[:index] + (default,) + aux[index + 1 :]


def _override_init_defaults_parent_classes(cls: type[T], defaults: dict) -> None:
    # Gather defaults for parameters in parent classes' __init__
    override_parent_params = []
    for base in inspect.getmro(cls)[1:]:
        if not defaults:
            break

        params = inspect.signature(base.__init__).parameters  # type: ignore[misc]
        names = [name for name in defaults if name in params]
        for name in names:
            new_param = inspect.Parameter(
                name=name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=defaults.pop(name),
                annotation=params[name].annotation,
            )
            override_parent_params.append(new_param)

    if not override_parent_params:
        return

    # Override defaults for parameters in parent classes' __init__ via a wrapper
    original_init = cls.__init__
    original_sig = inspect.signature(cls.__init__)
    parameters = list(original_sig.parameters.values())

    # Add the new parameters, keeping the **kwargs parameter last if it exists
    kwargs_param = None
    if parameters and parameters[-1].kind == inspect.Parameter.VAR_KEYWORD:
        kwargs_param = parameters.pop()
    parameters.extend(override_parent_params)
    if kwargs_param:
        parameters.append(kwargs_param)

    # Create and set __init__ wrapper with new signature
    parent_defaults = {p.name: p.default for p in override_parent_params}

    @wraps(original_init)
    def wrapper(*args, **kwargs):
        return original_init(*args, **{**parent_defaults, **kwargs})

    wrapper.__signature__ = original_sig.replace(parameters=parameters)  # type: ignore[attr-defined]
    cls.__init__ = wrapper  # type: ignore[method-assign]
