"""Collection of useful actions to define arguments."""

import re
import sys
from argparse import SUPPRESS, _HelpAction, _VersionAction
from argparse import Action as ArgparseAction
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from ._common import Action, NonParsingAction, get_parsing_setting, is_subclass, is_subclasses_disabled, parser_context
from ._loaders_dumpers import get_loader_exceptions, load_value
from ._namespace import Namespace
from ._optionals import _get_config_read_mode, ruamel_support
from ._paths import change_to_path_dir
from ._type_checking import ArgumentParser
from ._util import (
    Path,
    argument_error,
    default_config_option_help,
    get_import_path,
    import_object,
    indent_text,
    iter_to_set_str,
    load_config_path_context,
    merge_config,
    parse_value_or_config,
)

__all__ = [
    "ActionFail",
    "ActionYesNo",
    "ActionParser",
]


def _is_action_value_list(action: ArgparseAction) -> bool:
    """Checks whether an action produces a list value.

    Args:
        action: An argparse action to check.

    Returns:
        bool: True if produces list otherwise False.
    """
    if action.nargs in {"*", "+"} or (isinstance(action.nargs, int) and action.nargs != 0):
        return True
    return False


def remove_actions(parser, types):
    def remove(actions):
        rm_actions = [a for a in actions if isinstance(a, types)]
        for action in rm_actions:
            actions.remove(action)

    remove(parser._actions)
    for action_group in parser._action_groups:
        remove(action_group._group_actions)


non_parsing_actions = (_HelpAction, _VersionAction, NonParsingAction)


def filter_non_parsing_actions(actions):
    if isinstance(actions, list):
        return [a for a in actions if not isinstance(a, non_parsing_actions)]
    return {k: a for k, a in actions.items() if not isinstance(a, non_parsing_actions)}


class ActionConfigFile(Action):
    """Action to indicate that an argument is a configuration file or a configuration string."""

    def __init__(self, **kwargs):
        """Initializer for ActionConfigFile instance."""
        if "default" in kwargs:
            self.set_default_error()
        opt_name = kwargs["option_strings"]
        opt_name = opt_name[0] if len(opt_name) == 1 else [x for x in opt_name if x[0:2] == "--"][0]
        if "." in opt_name:
            raise ValueError("ActionConfigFile must be a top level option.")
        if "help" not in kwargs:
            kwargs["help"] = "Path to a configuration file."
        super().__init__(**kwargs)

    def __call__(self, parser, cfg, values, option_string=None):
        """Parses the given configuration and adds all the corresponding keys to the namespace.

        Raises:
            TypeError: If there are problems parsing the configuration.
        """
        self.apply_config(parser, cfg, self.dest, values)

    @staticmethod
    def set_default_error():
        raise ValueError("ActionConfigFile does not accept a default, use default_config_files.")

    @staticmethod
    def _ensure_single_config_argument(container, action):
        if (action == "config" or is_subclass(action, ActionConfigFile)) and any(
            isinstance(a, ActionConfigFile) for a in container._actions
        ):
            raise ValueError("A parser is only allowed to have a single 'config' argument.")

    @staticmethod
    def _add_print_config_argument(container, action):
        if isinstance(action, ActionConfigFile) and getattr(container, "_print_config", None) is not None:
            if "%s" in container._print_config:
                container._print_config = container._print_config % action.dest
            assert container._print_config.startswith("--")
            container.add_argument(container._print_config, action=_ActionPrintConfig)

    @staticmethod
    def apply_config(parser, cfg, dest, value) -> None:
        from ._link_arguments import skip_apply_links

        with parser_context(single_subcommand=False), previous_config_context(cfg), skip_apply_links():
            kwargs = {"env": False, "defaults": False, "_skip_validation": True, "_fail_no_subcommand": False}
            try:
                cfg_path: Path | None = Path(value, mode=_get_config_read_mode())
            except TypeError as ex_path:
                try:
                    if isinstance(load_value(value), str):
                        raise ex_path
                    cfg_path = None
                    cfg_file = parser.parse_string(value, **kwargs)
                except (TypeError, ValueError) + get_loader_exceptions() as ex_str:
                    raise TypeError(f'Parser key "{dest}": {ex_str}') from ex_str
            else:
                cfg_file = parser.parse_path(value, **kwargs)
            cfg_merged = merge_config(parser, cfg_file, cfg)
            cfg.__dict__.update(cfg_merged.__dict__)
            if cfg.get(dest) is get_parsing_setting("unset_sentinel"):
                cfg[dest] = []
            cfg[dest].append(cfg_path)

    def completer(self, prefix, **kwargs):
        from ._completions import get_files_completer

        files_completer = get_files_completer()
        return sorted(files_completer(prefix, **kwargs))


previous_config: ContextVar = ContextVar("previous_config", default=None)


@contextmanager
def previous_config_context(cfg):
    token = previous_config.set(cfg)
    try:
        yield
    finally:
        previous_config.reset(token)


print_config_skip: ContextVar = ContextVar("print_config_skip", default=False)


class _ActionPrintConfig(NonParsingAction):
    def __init__(
        self,
        option_strings,
        dest=SUPPRESS,
        default=SUPPRESS,
    ):
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=1,
            metavar="\b[=flags]",
            help=(
                "Print the configuration after applying all other arguments and exit. The optional "
                "flags customizes the output and are one or more keywords separated by comma. The "
                "supported flags are:%s skip_default, skip_unset."
            )
            % (" comments," if ruamel_support else ""),
        )

    def __call__(self, parser, namespace, value, option_string=None):
        kwargs = {"subparser": parser, "key": None, "skip_unset": False, "skip_validation": False}
        valid_flags = {"": None, "skip_default": "skip_default", "skip_unset": "skip_unset"}
        if ruamel_support:
            valid_flags["comments"] = "with_comments"
        flags = value[0].split(",")
        invalid_flags = [f for f in flags if f not in valid_flags]
        if len(invalid_flags) > 0:
            raise argument_error(f'Invalid option "{invalid_flags[0]}" for {option_string}')
        for flag in [f for f in flags if f != ""]:
            kwargs[valid_flags[flag]] = True
        while hasattr(parser, "parent_parser"):
            kwargs["key"] = parser.subcommand if kwargs["key"] is None else parser.subcommand + "." + kwargs["key"]
            parser = parser.parent_parser
        parser.print_config = kwargs

    @staticmethod
    @contextmanager
    def skip_print_config():
        t = print_config_skip.set(True)
        try:
            yield
        finally:
            print_config_skip.reset(t)

    @staticmethod
    def print_config_if_requested(parser, cfg):
        if hasattr(parser, "print_config") and not print_config_skip.get():
            key = parser.print_config.pop("key")
            subparser = parser.print_config.pop("subparser")
            if key is not None:
                cfg = cfg[key]
            with parser_context(lenient_check=True):
                sys.stdout.write(subparser.dump(cfg, **parser.print_config))
            delattr(parser, "print_config")
            parser.exit()

    @staticmethod
    def is_print_config_requested(parser):
        while parser:
            if hasattr(parser, "print_config"):
                return True
            parser = getattr(parser, "parent_parser", None)
        return False


class _ActionConfigLoad(Action):
    def __init__(self, basetype: type | None = None, **kwargs):
        if len(kwargs) == 0:
            self._basetype = basetype
        else:
            self.basetype = kwargs.pop("_basetype", None)
            kwargs["metavar"] = "CONFIG"
            kwargs["help"] = default_config_option_help
            kwargs["default"] = SUPPRESS
            super().__init__(**kwargs)

    def __call__(self, *args, **kwargs):
        if len(args) == 0:
            kwargs["_basetype"] = self._basetype
            return _ActionConfigLoad(**kwargs)
        parser, namespace, value = args[:3]
        loaded_value = self._load_config(value, parser)
        if isinstance(namespace.get(self.dest), Namespace):
            loaded_value = merge_config(
                parser, Namespace({self.dest: loaded_value}), Namespace({self.dest: namespace[self.dest]})
            )[self.dest]
        namespace[self.dest] = loaded_value
        return None

    def _load_config(self, value, parser):
        try:
            cfg, cfg_path = parse_value_or_config(value)
            if not isinstance(cfg, dict):
                raise TypeError(f'Parser key "{self.dest}": Unable to load config "{value}"')
            with load_config_path_context(cfg_path), change_to_path_dir(cfg_path):
                cfg = parser._apply_actions(cfg, parent_key=self.dest)
            return cfg
        except (TypeError,) + get_loader_exceptions() as ex:
            str_ex = indent_text(f"- {ex}")
            raise TypeError(f'Parser key "{self.dest}":\nUnable to load config {value!r}\n{str_ex}') from ex

    def check_type(self, value, parser):
        return self._load_config(value, parser)


class _ActionHelpClassPath(NonParsingAction):
    sub_add_kwargs: dict[str, Any] = {}

    @classmethod
    def get_help_types(cls, typehint) -> tuple | None:
        from ._typehints import get_subclass_or_closed_types

        return get_subclass_or_closed_types(typehint=typehint, also_lists=True, callable_return=True)

    def __init__(self, typehint=None, **kwargs):
        if typehint is not None:
            self._typehint = typehint
        else:
            self.update_init_kwargs(kwargs)
            super().__init__(**kwargs)

    def update_init_kwargs(self, kwargs):
        from ._typehints import is_protocol

        self._typehint = kwargs.pop("_typehint")
        self._help_types = self.get_help_types(self._typehint)
        assert self._help_types and all(isinstance(b, type) for b in self._help_types)
        self._single_class = len(self._help_types) == 1 and is_subclasses_disabled(self._help_types[0])
        self._basename = iter_to_set_str(t.__name__ for t in self._help_types)

        if len(self._help_types) == 1:
            kwargs["nargs"] = 0 if self._single_class else "?"

        if self._single_class:
            msg = ""
        else:
            kwargs["metavar"] = "CLASS_PATH_OR_NAME"
            self._kind = "subclass of"
            if any(is_protocol(b) for b in self._help_types):
                self._kind = "subclass or implementer of protocol"
            msg = f"the given {self._kind} "

        kwargs["default"] = SUPPRESS
        kwargs["help"] = f"Show the help for {msg}{self._basename} and exit."

    def __call__(self, *args, **kwargs):
        if len(args) == 0:
            kwargs["_typehint"] = self._typehint
            return type(self)(**kwargs)
        return self.print_help(args)

    def print_help(self, call_args):
        from ._typehints import (
            adapt_partial_callable_class,
            implements_protocol,
            resolve_class_path_by_name,
        )

        parser, _, value, option_string = call_args
        try:
            if self.nargs == 0 or (self.nargs == "?" and value is None):
                val_class = self._help_types[0]
            else:
                val_class = import_object(resolve_class_path_by_name(self._help_types, value))
        except Exception as ex:
            raise TypeError(f"{option_string}: {ex}") from ex

        if not any(is_subclass(val_class, b) or implements_protocol(val_class, b) for b in self._help_types):
            raise TypeError(f'{option_string}: Class "{value}" is not a {self._kind} {self._basename}')
        dest = re.sub("\\.help$", "", self.dest)
        subparser = type(parser)(description=f"Help for {option_string}={get_import_path(val_class)}")
        val = Namespace(class_path=get_import_path(val_class))
        sub_add_kwargs = dict(self.sub_add_kwargs)
        if "skip" in sub_add_kwargs:
            sub_add_kwargs["skip"] = set(sub_add_kwargs["skip"])
        _, partial_skip_args = adapt_partial_callable_class(self._typehint, val)
        if partial_skip_args:
            sub_add_kwargs.setdefault("skip", set()).update(partial_skip_args)
        subparser.add_class_arguments(val_class, dest, **sub_add_kwargs)
        subparser._inner_parser = True
        remove_actions(subparser, (_HelpAction, _ActionPrintConfig, _ActionConfigLoad))
        args = self.get_args_after_opt(parser.args)
        if args:
            subparser.parse_args(args)
            raise argument_error(f"Expected a nested --*.help option, got: {args}.")
        else:
            subparser.print_help()
            parser.exit()

    def get_args_after_opt(self, args):
        opt_str = self.option_strings[0]
        for num, arg in enumerate(args):
            parts = arg.split("=", 1)
            if parts[0] == opt_str:
                if len(parts) == 1:
                    num += 1
                break
        return args[num + 1 :]


class ActionFail(Action):
    """Action that always fails parsing with a given error."""

    def __init__(self, message: str = "option unavailable", **kwargs):
        """Initializer for ActionFail instance.

        Args:
            message: Text for the error to show. Use ``%(option)s``/``%(value)s`` to include the option and/or value.
        """
        if len(kwargs) == 0:
            self._message = message
        else:
            self._message = kwargs.pop("_message")
            kwargs["default"] = SUPPRESS
            kwargs["required"] = False
            if kwargs["option_strings"] == []:
                kwargs["nargs"] = "?"
            super().__init__(**kwargs)

    def __call__(self, *args, **kwargs):
        """Always fails with given message."""
        if len(args) == 0:
            kwargs["_message"] = self._message
            return ActionFail(**kwargs)
        parser, _, value, option = args
        parser.error(self._message % {"value": value, "option": option})


class ActionYesNo(Action):
    """Paired options ``--[yes_prefix]opt``, ``--[no_prefix]opt`` to set ``True`` or ``False`` respectively."""

    def __init__(self, yes_prefix: str = "", no_prefix: str = "no_", **kwargs):
        """Initializer for ActionYesNo instance.

        Args:
            yes_prefix: Prefix for yes option.
            no_prefix: Prefix for no option.

        Raises:
            ValueError: If a parameter is invalid.
        """
        if len(kwargs) == 0:
            self._yes_prefix = yes_prefix
            self._no_prefix = no_prefix
        else:
            self._yes_prefix = kwargs.pop("_yes_prefix") if "_yes_prefix" in kwargs else ""
            self._no_prefix = kwargs.pop("_no_prefix") if "_no_prefix" in kwargs else "no_"
            if len(kwargs["option_strings"]) == 0:
                raise ValueError(f"{type(self).__name__} not intended for positional arguments  ({kwargs['dest']}).")
            opt_name = kwargs["option_strings"][0]
            if not opt_name.startswith("--" + self._yes_prefix):
                raise ValueError(f'Expected option string to start with "--{self._yes_prefix}".')
            if self._no_prefix is not None:
                kwargs["option_strings"] += [re.sub("^--" + self._yes_prefix, "--" + self._no_prefix, opt_name)]
            if self._no_prefix is None and "nargs" in kwargs and kwargs["nargs"] != 1:
                raise ValueError("ActionYesNo with no_prefix=None only supports nargs=1.")
            if "nargs" in kwargs and kwargs["nargs"] in {"?", 1}:
                kwargs["metavar"] = "{true,yes,false,no}"
                if kwargs["nargs"] == 1:
                    kwargs["nargs"] = None
            else:
                kwargs["nargs"] = 0
                kwargs["metavar"] = None
            if "default" not in kwargs:
                kwargs["default"] = False
            kwargs["type"] = ActionYesNo._boolean_type
            super().__init__(**kwargs)

    def __call__(self, *args, **kwargs):
        """Sets the corresponding key to True or False depending on the option string used."""
        if len(args) == 0:
            kwargs["_yes_prefix"] = self._yes_prefix
            kwargs["_no_prefix"] = self._no_prefix
            return ActionYesNo(**kwargs)
        value = args[2] if isinstance(args[2], bool) else True
        if self._no_prefix is not None and args[3].startswith("--" + self._no_prefix):
            setattr(args[1], self.dest, not value)
        else:
            setattr(args[1], self.dest, value)
        return None

    def _add_dest_prefix(self, prefix):
        self.dest = prefix + "." + self.dest
        self.option_strings[0] = re.sub(
            "^--" + self._yes_prefix, "--" + self._yes_prefix + prefix + ".", self.option_strings[0]
        )
        if self._no_prefix is not None:
            self.option_strings[-1] = re.sub(
                "^--" + self._no_prefix, "--" + self._no_prefix + prefix + ".", self.option_strings[-1]
            )

    def _check_type(self, value):
        return ActionYesNo._boolean_type(value)

    @staticmethod
    def _boolean_type(x):
        if isinstance(x, str) and x.lower() in {"true", "yes", "false", "no"}:
            x = True if x.lower() in {"true", "yes"} else False
        elif not isinstance(x, bool):
            raise TypeError(f"Value not boolean: {x}.")
        return x

    def completer(self, **kwargs):
        """Used by argcomplete to support tab completion of arguments."""
        return ["true", "false", "yes", "no"]


class ActionParser:
    """Action to parse option with a given parser optionally loading from file if string value."""

    def __init__(
        self,
        parser: ArgumentParser,
    ):
        """Initializer for ActionParser instance.

        Args:
            parser: A parser to parse the option with.

        Raises:
            ValueError: If the parser parameter is invalid.
        """
        self._parser = parser
        if not isinstance(self._parser, import_object("jsonargparse.ArgumentParser")):
            raise ValueError("Expected parser keyword argument to be an ArgumentParser.")

    @staticmethod
    def _is_valid_action_parser(parser, action) -> bool:
        if not isinstance(action, ActionParser):
            return False
        if action._parser == parser:
            raise ValueError("Parser cannot be added as a subparser of itself.")
        return True

    @staticmethod
    def _move_parser_actions(parser, args, kwargs):
        subparser = kwargs.pop("action")._parser
        title = kwargs.pop("title", kwargs.pop("help", None))
        description = kwargs.pop("description", subparser.description)
        if len(kwargs) > 0:
            raise ValueError(f"ActionParser does not accept the following parameters: {set(kwargs)}")
        if not (len(args) == 1 and args[0].startswith("--")):
            raise ValueError(f"ActionParser only accepts a single optional key but got {args}")
        prefix = args[0][2:]

        def add_prefix(key):
            return re.sub("^--", "--" + prefix + ".", key)

        option_string_actions = {}
        for key, action in filter_non_parsing_actions(subparser._option_string_actions).items():
            option_string_actions[add_prefix(key)] = action

        isect = set(option_string_actions).intersection(set(parser._option_string_actions))
        if len(isect) > 0:
            raise ValueError(f"ActionParser conflicting keys: {isect}")

        actions = []
        dest = prefix.replace("-", "_")
        for action in filter_non_parsing_actions(subparser._actions):
            if isinstance(action, ActionYesNo):
                action._add_dest_prefix(prefix)
            else:
                action.dest = dest + "." + action.dest
                action.option_strings = [add_prefix(key) for key in action.option_strings]
            actions.append(action)

        base_action_group = subparser._action_groups[1]
        base_action_group.title = title
        if description is not None:
            base_action_group.description = description
        base_action_group.parser = parser
        base_action_group._actions = filter_non_parsing_actions(base_action_group._actions)
        base_action_group._group_actions = filter_non_parsing_actions(base_action_group._group_actions)
        extra_action_groups = subparser._action_groups[2:]
        for group in extra_action_groups:
            if group.dest is not None:
                group.dest = dest + "." + group.dest

        parser.add_argument(args[0], action=_ActionConfigLoad)
        parser._option_string_actions.update(option_string_actions)
        parser._actions.extend(actions)
        parser._action_groups.extend([base_action_group] + extra_action_groups)

        subparser._option_string_actions = {}
        subparser._actions = []
        subparser._action_groups = []

        return base_action_group
