import argparse
import inspect
import locale
import os
import re
from collections import defaultdict
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from copy import copy
from enum import Enum
from importlib.util import find_spec
from subprocess import PIPE, Popen
from typing import Literal, Union

from ._actions import ActionConfigFile, _ActionConfigLoad, _ActionHelpClassPath, remove_actions
from ._common import NonParsingAction, get_optionals_as_positionals_actions, get_parsing_setting
from ._parameter_resolvers import get_signature_parameters
from ._typehints import (
    ActionTypeHint,
    callable_origin_types,
    get_all_subclass_paths,
    get_callable_return_type,
    get_typehint_origin,
    is_subclass,
    type_to_str,
)
from ._util import NoneType, Path, import_object, merge_config, unique


def handle_completions(parser):
    handle_argcomplete_autocomplete(parser)
    add_print_completion_argument(parser)


def add_print_completion_argument(parser):
    if getattr(parser, "parent_parser", None) or not find_spec("shtab"):
        return
    print_completion_argument = get_parsing_setting("add_print_completion_argument")
    if print_completion_argument and "--print_completion" not in parser._option_string_actions:
        parser.add_argument("--print_completion", action=PrintCompletionAction)


# argcomplete


def handle_argcomplete_autocomplete(parser):
    if find_spec("argcomplete") and "_ARGCOMPLETE" in os.environ:
        import argcomplete

        from ._common import parser_context

        patch_argcomplete_support()
        with parser_context(load_value_mode=parser.parser_mode):
            argcomplete.autocomplete(parser)


def patch_argcomplete_support():
    import argcomplete.finders

    parse_known_args = argcomplete.finders.IntrospectiveArgumentParser.parse_known_args
    if getattr(parse_known_args, "__jsonargparse_patched__", False):
        return

    def parse_known_args(self, args=None, namespace=None):
        return self._parse_known_args_internal(args=args, namespace=namespace, argcomplete=True)

    parse_known_args.__jsonargparse_patched__ = True
    argcomplete.finders.IntrospectiveArgumentParser.parse_known_args = parse_known_args


def get_argcomplete_namespace(parser, namespace):
    namespace.__class__ = __import__("jsonargparse").Namespace
    return merge_config(parser, parser.get_defaults(skip_validation=True), namespace).as_flat()


def get_files_completer():
    from argcomplete.completers import FilesCompleter

    return FilesCompleter()


def argcomplete_warn_redraw_prompt(prefix, message):
    import argcomplete

    if prefix != "":
        argcomplete.warn(message)
        with suppress(Exception):
            proc = Popen(f"ps -p {os.getppid()} -oppid=".split(), stdout=PIPE, stderr=PIPE)
            stdout, _ = proc.communicate()
            shell_pid = int(stdout.decode().strip())
            os.kill(shell_pid, 28)
    _ = "_" if locale.getlocale()[1] != "UTF-8" else "\xa0"
    return [_ + message.replace(" ", _), ""]


# shtab

shtab_shell: ContextVar = ContextVar("shtab_shell")
shtab_prog: ContextVar = ContextVar("shtab_prog")
shtab_preambles: ContextVar = ContextVar("shtab_preambles")


class PrintCompletionAction(NonParsingAction):
    def __init__(
        self,
        option_strings,
        dest=argparse.SUPPRESS,
        default=argparse.SUPPRESS,
        **kwargs,
    ):
        import shtab

        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            choices=[f"shtab-{shell}" for shell in shtab.SUPPORTED_SHELLS],
            help="Print shell completion script.",
        )

    def __call__(self, parser, namespace, completion_type, option_string=None):
        print(parser.get_completion_script(completion_type))
        argparse.ArgumentParser.exit(parser, 0)


def get_completion_script(parser, completion_type: str, **kwargs) -> str:
    if not completion_type.startswith("shtab-"):
        raise ValueError(f"Unsupported completion_type: {completion_type}.")
    if not find_spec("shtab"):
        raise ValueError(f"shtab package is required for completion type '{completion_type}'.")
    return get_shtab_script(parser, completion_type[len("shtab-") :], **kwargs)


def get_shtab_script(parser, shell: str, preambles: list[str] | None = None) -> str:
    import shtab

    if shell not in shtab.SUPPORTED_SHELLS:
        raise ValueError(f"Unsupported completion_type: shtab-{shell}.")

    prog = norm_name(parser.prog)
    assert prog
    if not preambles:
        preambles = []
    if shell == "bash":
        preambles += [bash_compgen_typehint.strip().replace("%s", prog)]
    with prepare_actions_context(shell, prog, preambles):
        shtab_prepare_actions(parser)
    return shtab.complete(parser, shell, preamble="\n".join(preambles))


@contextmanager
def prepare_actions_context(shell, prog, preambles):
    token_shell = shtab_shell.set(shell)
    token_prog = shtab_prog.set(prog)
    token_preambles = shtab_preambles.set(preambles)
    try:
        yield
    finally:
        shtab_shell.reset(token_shell)
        shtab_prog.reset(token_prog)
        shtab_preambles.reset(token_preambles)


def norm_name(name: str) -> str:
    return re.sub(r"\W+", "_", name)


def shtab_prepare_actions(parser) -> None:
    remove_actions(parser, (PrintCompletionAction,))
    if parser._subcommands_action:
        for subparser in parser._subcommands_action._name_parser_map.values():
            shtab_prepare_actions(subparser)
    if get_parsing_setting("parse_optionals_as_positionals"):
        for action in get_optionals_as_positionals_actions(parser):
            clone = copy(action)
            clone.option_strings = []
            clone.nargs = "?"
            parser._actions.append(clone)
    for action in parser._actions:
        shtab_prepare_action(action, parser)


def shtab_prepare_action(action, parser) -> None:
    import shtab

    if action.choices or hasattr(action, "complete"):
        return

    complete = None
    if isinstance(action, (ActionConfigFile, _ActionConfigLoad)):
        complete = shtab.FILE
    elif isinstance(action, ActionTypeHint):
        typehint = action._typehint
        if get_typehint_origin(typehint) == Union:
            assert hasattr(typehint, "__args__")
            subtypes = [s for s in typehint.__args__ if s not in {NoneType, str, dict, list, tuple, bytes}]
            if len(subtypes) == 1:
                typehint = subtypes[0]
        if is_subclass(typehint, Path):
            assert hasattr(typehint, "_mode")
            if "f" in typehint._mode:
                complete = shtab.FILE
            elif "d" in typehint._mode:
                complete = shtab.DIRECTORY
        elif is_subclass(typehint, os.PathLike):
            complete = shtab.FILE
    if complete:
        action.complete = complete
        return

    choices = None
    if isinstance(action, ActionTypeHint):
        skip = getattr(action, "sub_add_kwargs", {}).get("skip", set())
        prefix = action.option_strings[0] if action.option_strings else None
        choices, require_prefix = get_typehint_choices(action._typehint, prefix, parser, skip)
        if shtab_shell.get() == "bash":
            message = f"Expected type: {type_to_str(action._typehint)}"
            if action.option_strings == []:
                message = f"Argument: {action.dest}; " + message
            add_bash_typehint_completion(
                parser,
                action,
                message,
                choices,
                require_prefix=require_prefix,
            )
            choices = None
    elif isinstance(action, _ActionHelpClassPath):
        choices = get_help_class_choices(action._typehint)
    if choices:
        action.choices = choices


bash_compgen_typehint_name = "_jsonargparse_%s_compgen_typehint"
bash_compgen_typehint = """
_jsonargparse_%%s_matched_choices() {
  local TOTAL=$(echo "$1" | wc -w | tr -d " ")
  if [ "$TOTAL" != 0 ]; then
    local MATCH=$(echo "$2" | wc -w | tr -d " ")
    printf "; $MATCH/$TOTAL matched choices"
  fi
}
%(name)s() {
  local REQUIRE_PREFIX="$4"
  local MATCH=()
  if [ "$REQUIRE_PREFIX" = 1 ] && [ -z "$2" ]; then
    MATCH=()
  else
    MATCH=( $(IFS=" " compgen -W "$1" "$2") )
  fi
  if [ ${#MATCH[@]} = 0 ]; then
    if [ "$COMP_TYPE" = 63 ]; then
      MATCHED=$(_jsonargparse_%%s_matched_choices "$1" "${MATCH[*]}")
      printf "%(b)s\\n$3$MATCHED\\n%(n)s" >&2
      kill -WINCH $$
    fi
  else
    for match in "${MATCH[@]}"; do
      echo "$match"
    done
    if [ "$COMP_TYPE" = 63 ]; then
      MATCHED=$(_jsonargparse_%%s_matched_choices "$1" "${MATCH[*]}")
      printf "%(b)s\\n$3$MATCHED%(n)s" >&2
    fi
  fi
}
""" % {
    "name": bash_compgen_typehint_name,
    "b": "$(tput setaf 5)",
    "n": "$(tput sgr0)",
}


def add_bash_typehint_completion(parser, action, message, choices, require_prefix=False) -> None:
    fn_typehint = norm_name(bash_compgen_typehint_name % shtab_prog.get())
    fn_name = parser.prog.replace(" [options] ", "_")
    fn_name = norm_name(f"_jsonargparse_{fn_name}_{action.dest}_typehint")
    fn = '{fn_name}(){{ {fn_typehint} "{choices}" "$1" "{message}" {require_prefix}; }}'.format(
        fn_name=fn_name,
        fn_typehint=fn_typehint,
        choices=" ".join(choices),
        message=message,
        require_prefix=1 if require_prefix else 0,
    )
    shtab_preambles.get().append(fn)
    action.complete = {"bash": fn_name}


def get_typehint_choices(typehint, prefix, parser, skip, added_subclasses=None) -> tuple[list[str], bool]:
    if not added_subclasses:
        added_subclasses = set()

    def get_choices_state(typehint) -> tuple[list[str], bool, bool]:
        if typehint is bool:
            return ["true", "false"], True, False
        if typehint is NoneType:
            return ["null"], True, False
        if is_subclass(typehint, Enum):
            return list(typehint.__members__), True, False

        origin = get_typehint_origin(typehint)
        if origin == Literal:
            choices = []
            for arg in typehint.__args__:
                if isinstance(arg, bool):
                    choices.append(str(arg).lower())
                elif arg is None:
                    choices.append("null")
                elif isinstance(arg, (str, int, float)):
                    choices.append(str(arg))
            return choices, True, False

        if origin == Union:
            choices = []
            has_explicit_choices = False
            has_open_values = False
            for subtype in typehint.__args__:
                if subtype in added_subclasses or subtype is object:
                    continue
                subchoices, subexplicit, subopen = get_choices_state(subtype)
                choices.extend(subchoices)
                has_explicit_choices = has_explicit_choices or subexplicit
                has_open_values = has_open_values or subopen
            return choices, has_explicit_choices, has_open_values

        if ActionTypeHint.is_subclass_typehint(typehint):
            added_subclasses.add(typehint)
            choices = add_subactions_and_get_subclass_choices(typehint, prefix, parser, skip, added_subclasses)
            return choices, True, False

        if origin in callable_origin_types:
            return_type = get_callable_return_type(typehint)
            if return_type and ActionTypeHint.is_subclass_typehint(return_type):
                num_args = len(typehint.__args__) - 1
                skip.add(num_args)
                choices = add_subactions_and_get_subclass_choices(return_type, prefix, parser, skip, added_subclasses)
                return choices, True, False
            return [], False, return_type is None

        return [], False, True

    choices, has_explicit_choices, has_open_values = get_choices_state(typehint)
    require_prefix = get_typehint_origin(typehint) == Union and has_explicit_choices and has_open_values
    return choices, require_prefix


def add_subactions_and_get_subclass_choices(typehint, prefix, parser, skip, added_subclasses) -> list[str]:
    choices = []
    paths = get_all_subclass_paths(typehint)
    init_args = defaultdict(list)
    subclasses = defaultdict(list)
    for path in paths:
        choices.append(path)
        try:
            cls = import_object(path)
            params = get_signature_parameters(cls, None, parser._logger)
        except Exception as ex:
            parser._logger.debug(f"Unable to get signature parameters for '{path}': {ex}")
            continue
        num_skip = next((s for s in skip if isinstance(s, int)), 0)
        if num_skip > 0:
            params = params[num_skip:]
        for param in params:
            if param.name not in skip:
                init_args[param.name].append(param.annotation)
                subclasses[param.name].append(path.rsplit(".", 1)[-1])

    if prefix is not None:
        for name, subtypes in init_args.items():
            option_string = f"{prefix}.{name}"
            if option_string not in parser._option_string_actions:
                action = parser.add_argument(option_string)
                for subtype in unique(subtypes):
                    subchoices, require_prefix = get_typehint_choices(
                        subtype, option_string, parser, skip, added_subclasses
                    )
                    if shtab_shell.get() == "bash":
                        message = f"Expected type: {type_to_str(subtype)}; "
                        message += f"Accepted by subclasses: {', '.join(subclasses[name])}"
                        add_bash_typehint_completion(
                            parser,
                            action,
                            message,
                            subchoices,
                            require_prefix=require_prefix,
                        )
                    elif subchoices:
                        action.choices = subchoices

    return choices


def get_help_class_choices(typehint) -> list[str]:
    choices = []
    if get_typehint_origin(typehint) == Union:
        for subtype in typehint.__args__:
            if inspect.isclass(subtype):
                choices.extend(get_help_class_choices(subtype))
    else:
        choices = get_all_subclass_paths(typehint)
    return choices
