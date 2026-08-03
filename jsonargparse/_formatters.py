"""Formatter classes."""

import re
from argparse import (
    OPTIONAL,
    SUPPRESS,
    ZERO_OR_MORE,
    Action,
    HelpFormatter,
    _HelpAction,
    _SubParsersAction,
)
from collections.abc import Iterable
from io import StringIO
from string import Template

from ._actions import (
    ActionConfigFile,
    ActionYesNo,
    _ActionConfigLoad,
    filter_non_parsing_actions,
    non_parsing_actions,
)
from ._common import (
    defaults_cache,
    get_optionals_as_positionals_actions,
    get_unaliased_type,
    is_subclasses_disabled,
    parent_parser,
    supports_optionals_as_positionals,
)
from ._deprecated import HelpFormatterDeprecations
from ._link_arguments import ActionLink
from ._namespace import Namespace
from ._optionals import import_ruamel
from ._subcommands import ActionSubCommands, find_action
from ._type_checking import ArgumentParser, ruamelCommentedMap
from ._typehints import (
    ActionTypeHint,
    get_optional_arg,
    get_subclass_or_closed_types,
    is_subclass_spec,
    type_to_str,
)

__all__ = ["DefaultHelpFormatter"]


class PercentTemplate(Template):
    delimiter = "%"
    pattern = r"""
    \%\((?:
    (?P<escaped>\%\%)|
    (?P<named>[_a-z][_a-z0-9]*)\)s|
    (?P<braced>[_a-z][_a-z0-9]*)\)s|
    (?P<invalid>)
    )
    """  # type: ignore[assignment]


def get_subparsers(parser: "ArgumentParser", prefix: str = "") -> dict[str | None, "ArgumentParser"]:
    """Returns the given parser and all its subcommand parsers, keyed by subcommand key."""
    parsers: dict[str | None, ArgumentParser] = {}
    if parser._subcommands_action is not None:
        for key, subparser in parser._subcommands_action._name_parser_map.items():
            full_key = (prefix + "." if prefix else "") + key
            parsers[full_key] = subparser
            parsers.update(get_subparsers(subparser, prefix=full_key))
    parsers[None] = parser
    return parsers


def get_group_titles(parser: "ArgumentParser") -> dict:
    """Returns a map of parser keys to the title of the group they belong to."""
    group_titles: dict = {}
    for parser_key, subparser in get_subparsers(parser).items():
        group_titles[parser_key] = subparser.description
        prefix = "" if parser_key is None else parser_key + "."
        for group in subparser._action_groups:
            actions = filter_non_parsing_actions(group._group_actions)
            skip_types = (_ActionConfigLoad, ActionConfigFile, ActionSubCommands)
            actions = [a for a in actions if not isinstance(a, skip_types)]
            keys = {re.sub(r"\.?[^.]+$", "", a.dest) for a in actions if "." in a.dest}
            for key in keys:
                group_titles[prefix + key] = group.title
    return group_titles


def get_class_group_title(class_parser: "ArgumentParser") -> str | None:
    """Returns the title of the group that a class parser adds for the class itself.

    The group for the class is the first one added, the rest correspond to nested keys.
    """
    groups = list((class_parser.groups or {}).values())
    return groups[0].title if groups else None


def get_class_parser(class_type, action: Action | None) -> "ArgumentParser | None":
    """Returns a parser for the arguments of a class, or None if not possible."""
    sub_add_kwargs = dict(getattr(action, "sub_add_kwargs", None) or {})
    sub_add_kwargs.pop("linked_targets", None)
    try:
        return ActionTypeHint.get_class_parser(class_type, sub_add_kwargs=sub_add_kwargs)
    except Exception:
        return None


def get_closed_type_parser(typehint, action: Action | None) -> "ArgumentParser | None":
    """Returns a parser for the arguments of a closed type, e.g. a dataclass, given its type hint."""
    types = get_subclass_or_closed_types(typehint, also_lists=True, callable_return=True)
    if types and len(types) == 1 and is_subclasses_disabled(types[0]):
        return get_class_parser(types[0], action)
    return None


def get_mapping_value_typehint(typehint):
    """Returns the type of the values of a mapping type hint, or None if not a mapping."""
    if not ActionTypeHint.is_mapping_typehint(typehint):
        return None
    args = getattr(get_optional_arg(get_unaliased_type(typehint)), "__args__", ())
    return args[1] if len(args) == 2 else None


def remove_leading_blank_line(cfg: ruamelCommentedMap) -> None:
    """Removes the blank line that comments add before the first key, needed for items of a list."""
    key = next(iter(cfg.keys()), None)
    comments = cfg.ca.items.get(key, [None, None])[1] if key is not None else None
    if comments and comments[0].value == "\n":
        del comments[0]


class YAMLCommentFormatter:
    """Formatter class for adding YAML comments to configuration files."""

    def __init__(self, help_formatter: HelpFormatter):
        self.help_formatter = help_formatter

    def add_yaml_comments(self, cfg: str) -> str:
        """Adds help text as yaml comments."""
        from ._core import ArgumentParser

        ruyaml = import_ruamel("add_yaml_comments")
        yaml = ruyaml.YAML()
        cfg = yaml.load(cfg)

        parser = parent_parser.get()
        assert isinstance(parser, ArgumentParser)
        if isinstance(cfg, dict):
            if parser.description is not None:
                self.set_yaml_start_comment(parser.description, cfg)
            self.set_comments(cfg, parser, get_group_titles(parser))
        out = StringIO()
        yaml.dump(cfg, out)
        return out.getvalue()

    def set_comments(
        self,
        cfg: ruamelCommentedMap,
        parser: "ArgumentParser",
        group_titles: dict,
        prefix: str = "",
        depth: int = 0,
    ) -> None:
        """Sets the comments for all the keys of a config object.

        Args:
            cfg: The ruamel.yaml object.
            parser: The parser from which help content is obtained.
            group_titles: Map of parser keys to the title of the group they belong to.
            prefix: The parser key that corresponds to the given config object.
            depth: The nested level of the keys of the config object.
        """
        for key in cfg.keys():
            full_key = (prefix + "." if prefix else "") + key
            action = find_action(parser, full_key)
            value = cfg[key]
            text = None
            if full_key in group_titles and isinstance(value, dict):
                text = group_titles[full_key]
            elif action is not None and action.help != SUPPRESS:
                text = self.help_formatter._expand_help(action)
            if isinstance(value, dict):
                if text:
                    self.set_yaml_group_comment(text, cfg, key, depth)
                self.set_dict_comments(value, action, depth + 1, parser, group_titles, full_key)
            else:
                if text:
                    self.set_yaml_argument_comment(text, cfg, key, depth)
                if isinstance(value, list):
                    self.set_list_comments(value, action, depth + 1)

    def set_dict_comments(
        self,
        cfg: ruamelCommentedMap,
        action: Action | None,
        depth: int,
        parser: "ArgumentParser | None" = None,
        group_titles: dict | None = None,
        prefix: str = "",
        typehint=None,
    ) -> None:
        """Sets the comments for the keys of a config object nested in another one.

        Args:
            cfg: The ruamel.yaml object.
            action: The action that corresponds to the given config object, if any.
            depth: The nested level of the keys of the config object.
            parser: The parser in which the keys are searched when not a class type.
            group_titles: Map of parser keys to the title of the group they belong to.
            prefix: The parser key that corresponds to the given config object.
            typehint: The type of the config object, defaults to the type of the action.
        """
        if is_subclass_spec(cfg):
            self.set_subclass_comments(cfg, action, depth)
            return
        if typehint is None and isinstance(action, ActionTypeHint):
            typehint = action._typehint
        class_parser = get_closed_type_parser(typehint, action)
        value_typehint = get_mapping_value_typehint(typehint)
        if class_parser is not None:
            self.set_comments(cfg, class_parser, get_group_titles(class_parser), depth=depth)
        elif value_typehint is not None:
            for value in cfg.values():
                if isinstance(value, dict):
                    self.set_dict_comments(value, action, depth + 1, typehint=value_typehint)
                elif isinstance(value, list):
                    self.set_list_comments(value, action, depth + 1, typehint=value_typehint)
        elif parser is not None:
            assert group_titles is not None
            self.set_comments(cfg, parser, group_titles, prefix, depth)

    def set_subclass_comments(self, cfg: ruamelCommentedMap, action: Action | None, depth: int) -> None:
        """Sets the comments for the init args of a subclass spec.

        Args:
            cfg: The ruamel.yaml object that has the class_path key.
            action: The action that corresponds to the given config object, if any.
            depth: The nested level of the keys of the config object.
        """
        init_args = cfg.get("init_args")
        if not isinstance(init_args, dict):
            return
        class_parser = get_class_parser(cfg["class_path"], action)
        if class_parser is None:
            return
        title = get_class_group_title(class_parser)
        if title:
            self.set_yaml_group_comment(title, cfg, "init_args", depth)
        self.set_comments(init_args, class_parser, get_group_titles(class_parser), depth=depth + 1)

    def set_list_comments(self, cfg: list, action: Action | None, depth: int, typehint=None) -> None:
        """Sets the comments for the class types that are items of a list.

        Args:
            cfg: The ruamel.yaml object.
            action: The action that corresponds to the given list.
            depth: The nested level of the keys of the items of the list.
            typehint: The type of the list, defaults to the type of the action.
        """
        for item in cfg:
            if isinstance(item, dict):
                self.set_dict_comments(item, action, depth, typehint=typehint)
                remove_leading_blank_line(item)
            elif isinstance(item, list):
                self.set_list_comments(item, action, depth + 1, typehint=typehint)

    def set_yaml_start_comment(
        self,
        text: str,
        cfg: ruamelCommentedMap,
    ):
        """Sets the start comment to a ruamel.yaml object.

        Args:
            text: The content to use for the comment.
            cfg: The ruamel.yaml object.
        """
        cfg.yaml_set_start_comment(text)

    def set_yaml_group_comment(
        self,
        text: str,
        cfg: ruamelCommentedMap,
        key: str,
        depth: int,
    ):
        """Sets the comment for a group to a ruamel.yaml object.

        Args:
            text: The content to use for the comment.
            cfg: The parent ruamel.yaml object.
            key: The key of the group.
            depth: The nested level of the group.
        """
        cfg.yaml_set_comment_before_after_key(key, before="\n" + text, indent=2 * depth)

    def set_yaml_argument_comment(
        self,
        text: str,
        cfg: ruamelCommentedMap,
        key: str,
        depth: int,
    ):
        """Sets the comment for an argument to a ruamel.yaml object.

        Args:
            text: The content to use for the comment.
            cfg: The parent ruamel.yaml object.
            key: The key of the argument.
            depth: The nested level of the argument.
        """
        cfg.yaml_set_comment_before_after_key(key, before="\n" + text, indent=2 * depth)


class DefaultHelpFormatter(HelpFormatterDeprecations, HelpFormatter):
    """Help message formatter that includes types, default values and env var names.

    This class is an extension of `argparse.HelpFormatter
    <https://docs.python.org/3/library/argparse.html#argparse.HelpFormatter>`_.
    Default values are always included. Furthermore, if the parser is configured
    with ``default_env=True`` command line options are preceded by ``ARG:`` and
    the respective environment variable name is included preceded by ``ENV:``.
    """

    def _get_help_string(self, action: Action) -> str:
        if getattr(action, "_jsonargparse_preexpanded_help", False):
            return action.help or ""
        action_help = action.help or ""
        if isinstance(action, ActionConfigFile):
            return action_help
        if isinstance(action, _HelpAction):
            help_str = action_help[0].upper() + action_help[1:]
            if help_str[-1] != ".":
                help_str += "."
            return help_str
        help_str = ""
        if action.required:
            help_str = "required"
        if "%(type)" not in action_help and self._get_type_str(action) is not None:
            help_str += (", " if help_str else "") + "type: %(type)s"
        if (
            "%(default)" not in action_help
            and action.default != SUPPRESS
            and (action.default is not None or not action.required)
            and (action.option_strings or action.nargs in {OPTIONAL, ZERO_OR_MORE})
        ):
            help_str += (", " if help_str else "") + "default: %(default)s"
        if isinstance(action, ActionTypeHint):
            help_str += action.extra_help()
        return action_help + (" (" + help_str + ")" if help_str else "")

    def _format_action(self, action: Action) -> str:
        if action.help is None and action.help != SUPPRESS:
            help_text = self._expand_help(action)
            if help_text and help_text.strip():
                action.help = help_text
                action._jsonargparse_preexpanded_help = True  # type: ignore[attr-defined]
                try:
                    return super()._format_action(action)
                finally:
                    del action._jsonargparse_preexpanded_help  # type: ignore[attr-defined]
                    action.help = None
        return super()._format_action(action)

    def _format_usage(self, usage, actions, *args, **kwargs) -> str:
        actions = filter_non_parsing_actions(actions)
        usage = super()._format_usage(usage, actions, *args, **kwargs)

        parser = parent_parser.get()
        if not parser:
            return usage

        if supports_optionals_as_positionals(parser):
            actions = get_optionals_as_positionals_actions(parser)
            if len(actions) > 0:
                extra_positionals = ""
                for action in reversed(actions):
                    extra_positionals = f"{action.dest} {extra_positionals}" if extra_positionals else action.dest
                    extra_positionals = f"[{extra_positionals}]"

                usage_lines = usage.rstrip().split("\n")
                last_line = usage_lines[-1] + " " + extra_positionals
                text_width = self._width - self._current_indent
                if len(usage_lines) == 1 or len(last_line) <= text_width:
                    usage_lines[-1] = last_line
                else:
                    indent = re.sub(r"^( +)[^ ].*$", r"\1", usage_lines[-1])
                    usage_lines.append(indent + extra_positionals)

                note = "note: extra positionals are parsed as optionals in the order shown above."
                usage = "\n".join(usage_lines) + f"\n\n{note}\n\n"

        return usage

    def _format_action_invocation(self, action: Action) -> str:
        parser = parent_parser.get()
        assert parser is not None
        if isinstance(action, ActionSubCommands):
            value = "Available subcommands:"
            if parser.default_env:
                value = f"ENV:   {get_env_var(self, action)}\n\n  {value}"
            return value
        if not parser.default_env:
            return super()._format_action_invocation(action)
        # Subcommand choices (individual subcommands in the list) don't get ARG: prefix or ENV: line
        if isinstance(action, _SubParsersAction._ChoicesPseudoAction):
            return super()._format_action_invocation(action)
        extr = ""
        if not isinstance(action, non_parsing_actions):
            extr += "\n  ENV:   " + get_env_var(self, action)
        return "ARG:   " + super()._format_action_invocation(action) + extr

    def _get_default_metavar_for_optional(self, action: Action) -> str:
        return action.dest.rsplit(".")[-1].upper()

    def _expand_help(self, action: Action) -> str:
        params = dict(vars(action), prog=self._prog)
        if params.get("choices") is not None:
            choices_str = ", ".join([str(c) for c in params["choices"]])
            params["choices"] = choices_str
        type_str = self._get_type_str(action)
        if type_str is not None:
            params["type"] = type_str
        orig_default = action.default
        if params.get("default") == SUPPRESS:
            del params["default"]
        elif "default" in params:
            defaults = defaults_cache.get()
            if defaults is not None:
                params["default"] = action.default = defaults.get(action.dest)
            if params["default"] is None:
                params["default"] = "null"
            elif isinstance(params["default"], Namespace):
                params["default"] = params["default"].as_dict()
        help_str = PercentTemplate(self._get_help_string(action)).safe_substitute(params)
        action.default = orig_default
        return help_str

    def _get_type_str(self, action: Action) -> str | None:
        type_str = None
        if isinstance(action, ActionYesNo):
            type_str = "bool"
        elif action.type is not None:
            type_str = type_to_str(action.type)
        elif isinstance(action, ActionTypeHint):
            type_str = type_to_str(action._typehint)
        return type_str

    def add_usage(self, usage: str | None, actions: Iterable[Action], *args, **kwargs) -> None:
        actions = [a for a in actions if not isinstance(a, ActionLink)]
        super().add_usage(usage, actions, *args, **kwargs)


def get_env_var(
    parser_or_formatter: ArgumentParser | DefaultHelpFormatter,
    action: Action | None = None,
) -> str:
    """Returns the environment variable name for a given parser or formatter and action."""
    if isinstance(parser_or_formatter, DefaultHelpFormatter):
        parser = parent_parser.get()
    else:
        parser = parser_or_formatter
    assert parser is not None
    env_var = ""
    if isinstance(parser.env_prefix, str):
        env_var = parser.env_prefix.replace("-", "_") + "_"
    if action:
        env_var += action.dest
    env_var = env_var.replace(".", "__").upper()
    return env_var
