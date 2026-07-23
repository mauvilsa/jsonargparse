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
    parent_parser,
    supports_optionals_as_positionals,
)
from ._link_arguments import ActionLink
from ._namespace import Namespace
from ._optionals import import_ruamel
from ._subcommands import ActionSubCommands, find_action
from ._type_checking import ArgumentParser, ruamelCommentedMap
from ._typehints import ActionTypeHint, type_to_str

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

        def get_parsers(parser: ArgumentParser, prefix="") -> dict[str | None, ArgumentParser]:
            parsers = {}
            if parser._subparsers is not None:
                for key, subparser in parser._subparsers._group_actions[0].choices.items():  # type: ignore[union-attr]
                    full_key = (prefix + "." if prefix else "") + key
                    parsers[full_key] = subparser
                    parsers.update(get_parsers(subparser, prefix=full_key))
            parsers[None] = parser
            return parsers

        parser = parent_parser.get()
        assert isinstance(parser, ArgumentParser)
        parsers = get_parsers(parser)

        group_titles = {}
        for parser_n_key, parser_n in parsers.items():
            group_titles[parser_n_key] = parser_n.description
            prefix = "" if parser_n_key is None else parser_n_key + "."
            for group in parser_n._action_groups:
                actions = filter_non_parsing_actions(group._group_actions)
                actions = [
                    a for a in actions if not isinstance(a, (_ActionConfigLoad, ActionConfigFile, ActionSubCommands))
                ]
                keys = {re.sub(r"\.?[^.]+$", "", a.dest) for a in actions if "." in a.dest}
                for key in keys:
                    group_titles[prefix + key] = group.title

        def set_comments(cfg, prefix="", depth=0):
            for key in cfg.keys():
                full_key = (prefix + "." if prefix else "") + key
                action = find_action(parser, full_key)
                text = None
                if full_key in group_titles and isinstance(cfg[key], dict):
                    text = group_titles[full_key]
                elif action is not None and action.help != SUPPRESS:
                    text = self.help_formatter._expand_help(action)
                if isinstance(cfg[key], dict):
                    if text:
                        self.set_yaml_group_comment(text, cfg, key, depth)
                    set_comments(cfg[key], full_key, depth + 1)
                elif text:
                    self.set_yaml_argument_comment(text, cfg, key, depth)

        if parser.description is not None:
            self.set_yaml_start_comment(parser.description, cfg)
        set_comments(cfg)
        out = StringIO()
        yaml.dump(cfg, out)
        return out.getvalue()

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


class DefaultHelpFormatter(HelpFormatter):
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
