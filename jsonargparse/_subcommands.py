"""Subcommands action and helper functions."""

from argparse import Action as ArgparseAction
from argparse import _SubParsersAction
from contextlib import contextmanager
from contextvars import ContextVar
from typing import NoReturn

from ._actions import filter_non_parsing_actions
from ._common import parsing_defaults, single_subcommand
from ._namespace import Namespace, NSKeyError, split_key, split_key_root
from ._type_checking import ActionsContainer, ArgumentParser
from ._util import merge_config

__all__ = ["ActionSubCommands"]


parse_kwargs: ContextVar = ContextVar("parse_kwargs", default={})


def is_branch_key(parser, key: str) -> bool:
    root_key = split_key_root(key)[0]
    for action in filter_non_parsing_actions(parser._actions):
        if isinstance(action, ActionSubCommands) and root_key in action._name_parser_map:
            subparser = action._name_parser_map[root_key]
            return is_branch_key(subparser, split_key_root(key)[1])
        elif action.dest.startswith(key + "."):
            return True
    return False


def find_action_and_subcommand(
    parser: ArgumentParser | ActionsContainer,
    dest: str,
    exclude: type[ArgparseAction] | tuple[type[ArgparseAction], ...] | None = None,
) -> tuple[ArgparseAction | None, str | None]:
    """Finds an action in a parser given its destination key."""
    actions = filter_non_parsing_actions(parser._actions)
    if exclude is not None:
        actions = [a for a in actions if not isinstance(a, exclude)]

    # Subcommand names should take precedence over option-string fallback
    # (e.g. subcommand "info" vs option "--info").
    for action in actions:
        if not isinstance(action, ActionSubCommands):
            continue
        if dest in action._name_parser_map:
            return action, None
        root_dest = split_key_root(dest)[0]
        if root_dest in action._name_parser_map:
            subcommand, subdest = split_key_root(dest)
            subparser = action._name_parser_map[subcommand]
            subaction, subsubcommand = find_action_and_subcommand(subparser, subdest, exclude=exclude)
            if subsubcommand is not None:
                subcommand += "." + subsubcommand
            return subaction, subcommand

    fallback_action = None
    for action in actions:
        if action.dest == dest or f"--{dest}" in action.option_strings:
            from ._actions import ActionFail, _ActionConfigLoad

            if isinstance(action, (_ActionConfigLoad, ActionFail)):
                fallback_action = action
            else:
                return action, None
    return fallback_action, None


def find_action(
    parser: ArgumentParser | ActionsContainer,
    dest: str,
    exclude: type[ArgparseAction] | tuple[type[ArgparseAction], ...] | None = None,
) -> ArgparseAction | None:
    return find_action_and_subcommand(parser, dest, exclude=exclude)[0]


def find_parent_action_and_subcommand(
    parser: ArgumentParser,
    key: str,
    exclude: type[ArgparseAction] | tuple[type[ArgparseAction], ...] | None = None,
) -> tuple[ArgparseAction | None, str | None]:
    action, subcommand = find_action_and_subcommand(parser, key, exclude=exclude)
    if action is None and "." in key:
        parts = split_key(key)
        for n in reversed(range(len(parts) - 1)):
            action, subcommand = find_action_and_subcommand(parser, ".".join(parts[: n + 1]), exclude=exclude)
            if action is not None:
                break
    return action, subcommand


def find_parent_action(
    parser: ArgumentParser,
    key: str,
    exclude: type[ArgparseAction] | tuple[type[ArgparseAction], ...] | None = None,
) -> ArgparseAction | None:
    return find_parent_action_and_subcommand(parser, key, exclude=exclude)[0]


class ActionSubCommands(_SubParsersAction):
    """Extension of argparse._SubParsersAction to modify subcommands functionality."""

    parent_parser: ArgumentParser
    env_prefix: str

    def add_parser(self, *args, **kwargs) -> NoReturn:
        """Raises a ``NotImplementedError`` since jsonargparse uses ``add_subcommand``."""
        raise NotImplementedError("In jsonargparse subcommands are added using the add_subcommand method.")

    def add_subcommand(self, name: str, parser: ArgumentParser, **kwargs) -> ArgumentParser:
        """Adds a parser as a subcommand parser.

        In contrast to `argparse.ArgumentParser.add_subparsers
        <https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_subparsers>`_
        add_parser requires to be given a parser as argument.

        Args:
            name: The name for the subcommand.
            parser: The parser to use for the subcommand.
        """
        if parser._subparsers is not None:
            raise ValueError("Multiple levels of subcommands must be added in level order.")
        if self.dest == name:
            raise ValueError(f"A subcommand name can't be the same as the subcommands dest: '{name}'.")

        parser.prog = f"{self._prog_prefix} [options] {name}"
        parser.env_prefix = f"{self.env_prefix}{name}_"
        parser.default_env = self.parent_parser.default_env
        parser.parent_parser = self.parent_parser  # type: ignore[attr-defined]
        parser.parser_mode = self.parent_parser.parser_mode
        parser.exit_on_error = self.parent_parser.exit_on_error
        parser.formatter_class = self.parent_parser.formatter_class
        parser.logger = self.parent_parser.logger
        parser.subcommand = name  # type: ignore[attr-defined]

        # create a pseudo-action to hold the choice help
        aliases = kwargs.pop("aliases", ())
        help_arg = None
        if "help" in kwargs:
            help_arg = kwargs.pop("help")
        choice_action = self._ChoicesPseudoAction(name, aliases, help_arg)
        self._choices_actions.append(choice_action)

        # add the parser to the name-parser map
        self._name_parser_map[name] = parser
        for alias in aliases:
            self._name_parser_map[alias] = parser

        return parser

    def __call__(self, parser, namespace, values, option_string=None):
        """Adds subcommand dest and parses subcommand arguments."""
        subcommand = values[0]
        arg_strings = values[1:]

        # set the parser name
        namespace[self.dest] = subcommand

        # parse arguments
        if subcommand in self._name_parser_map:
            subparser = self._name_parser_map[subcommand]
            subnamespace = namespace.get(subcommand).clone() if subcommand in namespace else None
            kwargs = dict(_skip_validation=True, _namespace_as_config=True, **parse_kwargs.get())
            namespace[subcommand] = subparser.parse_args(arg_strings, namespace=subnamespace, **kwargs)


@contextmanager
def parse_kwargs_context(kwargs):
    parse_kwargs.set(kwargs)
    yield


def get_subcommands(
    parser: ArgumentParser,
    cfg: Namespace,
    prefix: str = "",
    fail_no_subcommand: bool = True,
) -> tuple[list[str] | None, list[ArgumentParser] | None]:
    """Returns subcommand names and corresponding subparsers."""
    if parser._subcommands_action is None:
        return None, None
    action = parser._subcommands_action

    require_single = single_subcommand.get() and not parsing_defaults.get()

    # Get subcommand settings keys
    subcommand_keys = [k for k in action.choices if isinstance(cfg.get(prefix + k), Namespace)]

    # Get subcommand
    subcommand = None
    dest = prefix + action.dest
    if dest in cfg and cfg.get(dest) is not None:
        subcommand = cfg[dest]
        if parsing_defaults.get():
            raise NSKeyError(f"A specific subcommand can't be provided in defaults, got '{subcommand}'")
    elif len(subcommand_keys) > 0 and (fail_no_subcommand or require_single):
        cfg[dest] = subcommand = subcommand_keys[0]
        if len(subcommand_keys) > 1:
            raise ValueError(
                f"Multiple subcommand settings ({', '.join(subcommand_keys)}) without providing an "
                f"explicit '{dest}' key."
            )

    # Remove extra subcommand settings
    if subcommand and len(subcommand_keys) > 1:
        for key in [k for k in subcommand_keys if k != subcommand]:
            del cfg[prefix + key]

    if subcommand:
        subcommand_keys = [subcommand]

    if fail_no_subcommand:
        if subcommand is None and not (fail_no_subcommand and action.required):
            return None, None
        if action.required and subcommand not in action._name_parser_map:
            # If subcommand is required and no subcommand is provided,
            # present the user with a friendly error message to remind them of
            # the available subcommands and to select one.
            available_subcommands = list(action._name_parser_map)
            if len(available_subcommands) <= 5:
                candidate_subcommands_str = "{" + ",".join(available_subcommands) + "}"
            else:
                candidate_subcommands_str = "{" + ",".join(available_subcommands[:5]) + ", ...}"
            raise NSKeyError(f'expected "{dest}" to be one of {candidate_subcommands_str}, but it was not provided.')

    return subcommand_keys, [action._name_parser_map.get(s) for s in subcommand_keys]  # type: ignore[misc]


def get_subcommand(
    parser: ArgumentParser,
    cfg: Namespace,
    prefix: str = "",
    fail_no_subcommand: bool = True,
) -> tuple[str | None, ArgumentParser | None]:
    """Returns a single subcommand name and corresponding subparser."""
    subcommands, subparsers = get_subcommands(
        parser,
        cfg,
        prefix=prefix,
        fail_no_subcommand=fail_no_subcommand,
    )
    return subcommands[0] if subcommands else None, subparsers[0] if subparsers else None


def handle_subcommands(
    parser: ArgumentParser,
    cfg: Namespace,
    env: bool | None,
    defaults: bool,
    prefix: str = "",
    fail_no_subcommand: bool = True,
) -> None:
    """Takes care of parsing subcommand values."""

    subcommands, subparsers = get_subcommands(parser, cfg, prefix=prefix, fail_no_subcommand=fail_no_subcommand)
    if not subcommands or not subparsers:
        return

    for subcommand, subparser in zip(subcommands, subparsers):
        # Merge environment variable values and default values
        subnamespace = None
        key = prefix + subcommand
        if env:
            subnamespace = subparser.parse_env(defaults=defaults, _skip_validation=True)
        elif defaults:
            subnamespace = subparser.get_defaults(skip_validation=True)

        # Update all subcommand settings
        if subnamespace is not None:
            cfg[key] = merge_config(subparser, cfg.get(key, Namespace()), subnamespace)

        # Handle inner subcommands
        if subparser._subparsers is not None:
            handle_subcommands(subparser, cfg, env, defaults, key + ".", fail_no_subcommand=fail_no_subcommand)
