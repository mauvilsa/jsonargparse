"""Extensions of core argparse classes."""

import argparse
import glob
import inspect
import logging
import os
import sys
from collections.abc import Callable, Sequence
from contextlib import suppress
from typing import (
    Any,
    NoReturn,
)

from ._actions import (
    ActionConfigFile,
    ActionParser,
    _ActionConfigLoad,
    _ActionPrintConfig,
    _is_action_value_list,
    filter_non_parsing_actions,
    previous_config,
)
from ._common import (
    debug_mode_active,
    get_optionals_as_positionals_actions,
    get_parsing_setting,
    is_subclasses_disabled,
    lenient_check,
    parser_context,
    supports_optionals_as_positionals,
    validate_default,
)
from ._completions import get_argcomplete_namespace, handle_completions
from ._completions import (
    get_completion_script as get_completion_script_internal,
)
from ._formatters import DefaultHelpFormatter, get_env_var
from ._instantiation import InstantiateMethod
from ._jsonnet import ActionJsonnet
from ._jsonschema import ActionJsonSchema
from ._link_arguments import ActionLink, ArgumentLinking
from ._loaders_dumpers import (
    check_valid_dump_format,
    dump_using_format,
    get_loader_exceptions,
    load_value,
    loaders,
)
from ._namespace import (
    Namespace,
    NSKeyError,
    get_non_meta_sorted_keys,
    is_meta_key,
    recreate_branches,
    remove_meta,
    split_key_leaf,
    split_key_root,
)
from ._optionals import (
    _get_config_read_mode,
    fsspec_support,
    import_fsspec,
    import_jsonnet,
    omegaconf_apply,
    pyyaml_available,
)
from ._parameter_resolvers import UnknownDefault
from ._paths import change_to_path_dir
from ._required import (
    iter_required_keys,
    restore_suppressed_required,
    set_required,
    suppress_required_actions,
)
from ._signatures import SignatureArguments
from ._subcommands import (
    ActionSubCommands,
    find_action,
    find_action_and_subcommand,
    find_parent_action_and_subcommand,
    get_subcommand,
    handle_subcommands,
    is_branch_key,
    parse_kwargs_context,
)
from ._typehints import ActionTypeHint, is_subclass_spec, subclasses_disabled_remove_class_path
from ._util import (
    Path,
    argument_error,
    get_argument_group_class,
    get_private_kwargs,
    identity,
    load_config_path_context,
    merge_config,
    return_parser_if_captured,
)

__all__ = ["ArgumentParser"]


_parse_known_has_intermixed = "intermixed" in inspect.signature(argparse.ArgumentParser._parse_known_args).parameters


class ActionsContainer(ArgumentLinking, InstantiateMethod, SignatureArguments, argparse._ActionsContainer):
    """Extension of ``argparse._ActionsContainer`` to support additional functionalities."""

    _action_groups: Sequence["ArgumentGroup"]  # type: ignore[assignment]

    def __init__(self, *args, **kwargs) -> None:
        """Initializer for ActionsContainer instance."""
        super().__init__(*args, **kwargs)
        self.register("type", None, identity)
        self.register("action", "parsers", ActionSubCommands)
        self.register("action", "config", ActionConfigFile)

    def add_argument(self, *args, sub_configs: bool = False, **kwargs):
        """Adds an argument to the parser or argument group.

        All the arguments from `argparse.ArgumentParser.add_argument
        <https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument>`_
        are supported. Additionally it accepts:

        Args:
            sub_configs: Whether to try parsing a sub-config when argument is a complex type.
        """
        parser = self.parser if hasattr(self, "parser") else self
        if kwargs.get("action") is not None:
            if ActionParser._is_valid_action_parser(parser, kwargs["action"]):
                return ActionParser._move_parser_actions(parser, args, kwargs)
            ActionConfigFile._ensure_single_config_argument(self, kwargs["action"])
        if "type" in kwargs:
            if is_subclasses_disabled(kwargs["type"]):
                nested_key = args[0].lstrip("-")
                self.add_class_arguments(kwargs.pop("type"), nested_key, sub_configs=sub_configs, **kwargs)
                return find_action(parser, nested_key)
            if ActionTypeHint.is_supported_typehint(kwargs["type"]):
                args = ActionTypeHint.prepare_add_argument(
                    args=args,
                    kwargs=kwargs,
                    enable_path=sub_configs,
                    container=super(),
                    logger=self._logger,
                )
        if "choices" in kwargs and not isinstance(kwargs["choices"], (list, tuple)):
            kwargs["choices"] = tuple(kwargs["choices"])
        action = super().add_argument(*args, **kwargs)
        action.logger = self._logger  # type: ignore[attr-defined]
        ActionConfigFile._add_print_config_argument(self, action)
        ActionJsonnet._check_ext_vars_action(parser, action)
        if is_meta_key(action.dest):
            raise ValueError(f'Argument with destination name "{action.dest}" not allowed.')
        if (
            action.option_strings == []
            and "default" in kwargs
            and kwargs["default"] is not argparse.SUPPRESS
            and action.nargs not in ("*", "?")
        ):
            raise ValueError("Positional arguments not allowed to have a default value.")
        unset_sentinel = get_parsing_setting("unset_sentinel")
        if unset_sentinel is not None and "default" not in kwargs and action.default is None:
            action.default = unset_sentinel
        validate_default(self, action)
        return action

    def add_argument_group(self, *args, name: str | None = None, **kwargs) -> "ArgumentGroup":
        """Adds a group to the parser.

        All the arguments from `argparse.ArgumentParser.add_argument_group
        <https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_argument_group>`_
        are supported. Additionally it accepts:

        Args:
            name: Name of the group. If set, the group object will be included in the ``parser.groups`` dict.

        Returns:
            The group object.

        Raises:
            ValueError: If a group with the same name already exists.
        """
        parser = self.parser if hasattr(self, "parser") else self
        if name is not None and name in parser.groups:  # type: ignore[union-attr]
            raise ValueError(f"Group with name {name} already exists.")
        group_class = getattr(parser, "_group_class", ArgumentGroup)
        group = group_class(parser, *args, logger=parser._logger, **kwargs)
        group.parser = parser
        parser._action_groups.append(group)  # type: ignore[union-attr]
        if name is not None:
            parser.groups[name] = group  # type: ignore[union-attr]
        return group

    def set_defaults(self, *args: dict[str, Any], **kwargs: Any) -> None:
        """Sets default values from dictionary or keyword arguments.

        Args:
            *args: Dictionary defining the default values to set.
            **kwargs: Sets default values based on keyword arguments.

        Raises:
            KeyError: If key not defined in the parser.
        """
        for arg in args:
            for dest, default in arg.items():
                dest = dest.replace("-", "_")
                action = find_action(self, dest)
                if action is None:
                    raise NSKeyError(f'No action for key "{dest}" to set its default.')
                elif isinstance(action, ActionConfigFile):
                    ActionConfigFile.set_default_error()
                elif isinstance(action, _ActionConfigLoad):
                    default = {f"{dest}.{k}": v for k, v in default.items()}
                    self.set_defaults(default)
                    continue
                if isinstance(action, ActionTypeHint):
                    default = action.normalize_default(default)
                self._defaults[dest] = action.default = default
        if kwargs:
            self.set_defaults(kwargs)


class ArgumentGroup(ActionsContainer, argparse._ArgumentGroup):
    """Extension of argparse._ArgumentGroup to support additional functionalities."""

    dest: str | None = None
    parser: "ArgumentParser | ActionsContainer | None" = None


class ArgumentParser(ActionsContainer, argparse.ArgumentParser):
    """Parser for command line, configuration files and environment variables."""

    formatter_class: type[argparse.HelpFormatter]
    groups: dict[str, ArgumentGroup] | None = None
    _group_class: type[ArgumentGroup]
    _subcommands_action: ActionSubCommands | None = None

    def __init__(
        self,
        *args,
        env_prefix: bool | str = True,
        formatter_class: type[argparse.HelpFormatter] = DefaultHelpFormatter,
        logger: logging.Logger | bool | str | dict = False,
        version: str | None = None,
        print_config: str | None = "--print_config",
        parser_mode: str = "yaml" if pyyaml_available else "json",
        dump_header: list[str] | None = None,
        default_config_files: list[str | os.PathLike] | None = None,
        default_env: bool = False,
        **kwargs,
    ) -> None:
        """Initializer for ArgumentParser instance.

        All the arguments from the initializer of `argparse.ArgumentParser
        <https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser>`_
        are supported. Additionally it accepts:

        Args:
            env_prefix: Prefix for environment variables. ``True`` to derive from ``prog``.
            formatter_class: Class for printing help messages.
            logger: Logger to use or configuration for logger.
            version: Program version which will be printed by the ``--version`` argument.
            print_config: Name for print config argument, ``%s`` is replaced by config dest, set ``None`` to disable.
            parser_mode: Mode for parsing values: ``yaml``, ``json``, ``jsonnet`` or added via :func:`.set_loader`.
            dump_header: Header to include as comment when dumping a config object.
            default_config_files: Default config file locations, e.g. ``['~/.config/myapp/*.yaml']``.
            default_env: Set the default value on whether to parse environment variables.
        """
        super().__init__(*args, formatter_class=formatter_class, logger=logger, **kwargs)
        self._group_class = get_argument_group_class(self)
        if self.groups is None:
            self.groups = {}
        self._extra_required_keys: set[str] = set()
        self.save_path_content: set[str] = set()
        self.default_config_files = default_config_files
        self.default_env = default_env
        self.env_prefix = env_prefix
        self.parser_mode = parser_mode
        self.dump_header = dump_header
        self._print_config = print_config
        if version is not None:
            self.add_argument(
                "--version", action="version", version="%(prog)s " + version, help="Print version and exit."
            )

    ## Parsing methods ##

    def _parse_known_args_internal(self, args=None, namespace=None, *, argcomplete: bool = False):
        if argcomplete:
            namespace = get_argcomplete_namespace(self, namespace)
        try:
            with (
                parser_context(parent_parser=self, lenient_check=True),
                ActionTypeHint.subclass_arg_context(self),
                suppress_required_actions(self),
            ):
                kwargs = {}
                if _parse_known_has_intermixed:
                    kwargs["intermixed"] = False
                namespace, args = self._parse_known_args(args, namespace, **kwargs)
        except argparse.ArgumentError as ex:
            self.error(str(ex), ex)

        return namespace, args

    def _positional_optionals(self, cfg, unk):
        if len(unk) == 0 or not supports_optionals_as_positionals(self):
            return cfg, unk

        for action in get_optionals_as_positionals_actions(self, include_positionals=True):
            if action.option_strings == []:
                if cfg.get(action.dest) is get_parsing_setting("unset_sentinel"):
                    self._logger.debug(f"Positional argument {action.dest} missing, aborting _positional_optionals")
                    break
                continue

            value = unk.pop(0)
            try:
                cfg[action.dest] = self._check_value_key(action, value, action.dest, cfg)
            except (TypeError, ValueError) as ex:
                if isinstance(value, str) and value.startswith("--"):
                    raise argument_error(f"unrecognized arguments: {' '.join([value] + unk)}") from ex
                raise

            if len(unk) == 0:
                break

        return cfg, unk

    def _parse_optional(self, arg_string):
        subclass_arg = ActionTypeHint.parse_argv_item(arg_string)
        if subclass_arg:
            return subclass_arg
        if arg_string == self._print_config:
            arg_string += "="
        return super()._parse_optional(arg_string)

    def _parse_common(
        self,
        cfg: Namespace,
        env: bool | None,
        defaults: bool,
        skip_validation: bool,
        skip_required: bool = False,
        skip_subcommands: bool = False,
        fail_no_subcommand: bool = True,
    ) -> Namespace:
        """Common parsing code used by other parse methods.

        Args:
            cfg: The configuration object.
            env: Whether to merge with the parsed environment, ``None`` to use the parser's default.
            defaults: Whether to merge with the parser's defaults.
            skip_validation: Whether to skip validation of configuration.
            skip_required: Whether to skip check of required arguments.
            skip_subcommands: Whether to skip subcommand processing.
            fail_no_subcommand: Whether to fail if no subcommand given.

        Returns:
            A config object with all parsed values.
        """
        if env is None and self._default_env:
            env = True

        if not skip_subcommands:
            handle_subcommands(self, cfg, env=env, defaults=defaults, fail_no_subcommand=fail_no_subcommand)

        if defaults:
            with parser_context(lenient_check=True):
                ActionTypeHint.add_sub_defaults(self, cfg)

        with parser_context(parent_parser=self):
            if not lenient_check.get() and self.parser_mode == "omegaconf+":
                cfg = omegaconf_apply(self, cfg)

            _ActionPrintConfig.print_config_if_requested(self, cfg)

            try:
                ActionLink.apply_parsing_links(self, cfg)
            except Exception as ex:
                self.error(str(ex), ex)

            if not skip_validation:
                self.validate(cfg, skip_required=skip_required)

        if not lenient_check.get():
            cfg = subclasses_disabled_remove_class_path(cfg)

        return cfg

    def _parse_defaults_and_environ(
        self,
        defaults: bool = True,
        env: bool | None = None,
        environ: dict[str, str] | os._Environ | None = None,
    ):
        cfg = Namespace()
        if defaults:
            with parser_context(lenient_check=True):  # required for omegaconf+
                cfg = self.get_defaults(skip_validation=True)

        if env or (env is None and self._default_env):
            if environ is None:
                environ = os.environ
            with parser_context(load_value_mode=self.parser_mode):
                cfg_env = self._load_env_vars(env=environ, defaults=defaults)
            cfg = merge_config(self, cfg_env, cfg)

        return cfg

    def parse_args(  # type: ignore[override]
        self,
        args: Sequence[str] | None = None,
        namespace: Namespace | None = None,
        env: bool | None = None,
        defaults: bool = True,
        **kwargs,
    ) -> Namespace:
        """Parses command line argument strings.

        All the arguments from `argparse.ArgumentParser.parse_args
        <https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.parse_args>`_
        are supported. Additionally it accepts:

        Args:
            args: List of arguments to parse or ``None`` to use ``sys.argv``.
            env: Whether to merge with the parsed environment, ``None`` to use the parser's default.
            defaults: Whether to merge with the parser's defaults.

        Returns:
            A config object with all parsed values.

        Raises:
            ArgumentError: If the parsing fails and ``exit_on_error=False``.
        """
        skip_validation, namespace_as_config = get_private_kwargs(
            kwargs, _skip_validation=False, _namespace_as_config=False
        )
        return_parser_if_captured(self)
        handle_completions(self)

        if args is None:
            args = sys.argv[1:]
        else:
            args = list(args)
            if not all(isinstance(a, str) for a in args):
                self.error(f"All arguments are expected to be strings: {args}")
        self.args = args

        try:
            cfg = self._parse_defaults_and_environ(defaults, env)
            if namespace:
                if namespace_as_config:
                    cfg = self._parse_defaults_and_environ(defaults, env=False)
                    cfg = merge_config(self, namespace, cfg)
                    if env or (env is None and self._default_env):
                        with parser_context(load_value_mode=self.parser_mode):
                            cfg_env = self._load_env_vars(env=os.environ, defaults=defaults)
                        cfg = merge_config(self, cfg_env, cfg)
                else:
                    cfg = merge_config(self, namespace, cfg)

            with parse_kwargs_context({"env": env, "defaults": defaults}):
                cfg, unk = self._parse_known_args_internal(args=args, namespace=cfg)
                cfg, unk = self._positional_optionals(cfg, unk)
            if unk:
                self.error(f"unrecognized arguments: {' '.join(unk)}")

            parsed_cfg = self._parse_common(
                cfg=cfg,
                env=env,
                defaults=defaults,
                skip_validation=skip_validation,
            )

        except (TypeError, KeyError, argparse.ArgumentError) as ex:
            self.error(str(ex), ex)

        self._logger.debug("Parsed command line arguments: %s", args)
        return parsed_cfg

    def parse_object(
        self,
        obj: Namespace | dict[str, Any],
        namespace: Namespace | None = None,
        env: bool | None = None,
        defaults: bool = True,
        **kwargs,
    ) -> Namespace:
        """Parses configuration given as an object.

        Args:
            obj: The configuration object.
            env: Whether to merge with the parsed environment, ``None`` to use the parser's default.
            defaults: Whether to merge with the parser's defaults.

        Returns:
            A config object with all parsed values.

        Raises:
            ArgumentError: If the parsing fails and ``exit_on_error=False``.
        """
        skip_validation, skip_required = get_private_kwargs(kwargs, _skip_validation=False, _skip_required=False)

        try:
            cfg = self._parse_defaults_and_environ(defaults, env)
            if namespace:
                cfg = merge_config(self, namespace, cfg)

            cfg = self._apply_actions(cfg)
            cfg_apply = self._apply_actions(obj, prev_cfg=cfg)
            cfg = merge_config(self, cfg_apply, cfg)

            parsed_cfg = self._parse_common(
                cfg=cfg,
                env=env,
                defaults=defaults,
                skip_validation=skip_validation,
                skip_required=skip_required,
            )

        except (TypeError, KeyError) as ex:
            self.error(str(ex), ex)

        self._logger.debug("Parsed object: %s", obj)
        return parsed_cfg

    def _load_env_vars(self, env: dict[str, str] | os._Environ, defaults: bool) -> Namespace:
        cfg = Namespace()
        actions = filter_non_parsing_actions(self._actions)
        for action in actions:
            env_var = get_env_var(self, action)
            if env_var in env and isinstance(action, ActionConfigFile):
                ActionConfigFile.apply_config(self, cfg, action.dest, env[env_var])
        for action in actions:
            env_var = get_env_var(self, action)
            if env_var in env and isinstance(action, ActionSubCommands):
                env_val = env[env_var]
                if env_val in action.choices:
                    cfg[action.dest] = subcommand = self._check_value_key(action, env_val, action.dest, cfg)
                    pcfg = action._name_parser_map[env_val].parse_env(env=env, defaults=defaults, _skip_validation=True)
                    for k, v in vars(pcfg).items():
                        cfg[subcommand + "." + k] = v
        for action in actions:
            env_var = get_env_var(self, action)
            if env_var in env and not isinstance(action, (ActionConfigFile, ActionSubCommands)):
                env_val = env[env_var]
                if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
                    env_val_lower = env_val.lower()
                    if env_val_lower == "true":
                        env_val = True
                    elif env_val_lower == "false":
                        env_val = False
                    else:
                        raise argparse.ArgumentError(
                            action, f"Invalid boolean value for environment variable {env_var}: {env_val}"
                        )
                elif _is_action_value_list(action):
                    try:
                        list_env_val = load_value(env_val)
                        env_val = list_env_val if isinstance(list_env_val, list) else [env_val]
                    except get_loader_exceptions():
                        env_val = [env_val]
                cfg[action.dest] = self._check_value_key(action, env_val, action.dest, cfg)
        self._apply_actions(cfg)
        return cfg

    def parse_env(
        self,
        env: dict[str, str] | None = None,
        defaults: bool = True,
        **kwargs,
    ) -> Namespace:
        """Parses environment variables.

        Args:
            env: The environment object to use, if ``None`` then ``os.environ`` is used.
            defaults: Whether to merge with the parser's defaults.

        Returns:
            A config object with all parsed values.

        Raises:
            ArgumentError: If the parsing fails and ``exit_on_error=False``.
        """
        skip_validation, skip_subcommands = get_private_kwargs(kwargs, _skip_validation=False, _skip_subcommands=False)

        try:
            cfg = self._parse_defaults_and_environ(defaults, env=True, environ=env)

            kwargs = {
                "env": True,
                "defaults": defaults,
                "skip_validation": skip_validation,
                "skip_subcommands": skip_subcommands,
            }
            if skip_validation:
                kwargs["fail_no_subcommand"] = False

            parsed_cfg = self._parse_common(cfg=cfg, **kwargs)

        except (TypeError, KeyError) as ex:
            self.error(str(ex), ex)

        self._logger.debug("Parsed environment variables")
        return parsed_cfg

    def parse_path(
        self,
        path: str | os.PathLike,
        ext_vars: dict | None = None,
        env: bool | None = None,
        defaults: bool = True,
        **kwargs,
    ) -> Namespace:
        """Parses a configuration file given its path.

        Args:
            path: Path to the configuration file to parse.
            ext_vars: Optional external variables used for parsing jsonnet.
            env: Whether to merge with the parsed environment, ``None`` to use the parser's default.
            defaults: Whether to merge with the parser's defaults.

        Returns:
            A config object with all parsed values.

        Raises:
            ArgumentError: If the parsing fails and ``exit_on_error=False``.
        """
        fpath = Path(path, mode=_get_config_read_mode())
        with load_config_path_context(fpath), change_to_path_dir(fpath):
            content = fpath.read_text()
            parsed_cfg = self.parse_string(
                content=content,
                path=os.path.basename(path),
                ext_vars=ext_vars,
                env=env,
                defaults=defaults,
                **kwargs,
            )

        self._logger.debug("Parsed configuration from path: %s", path)
        return parsed_cfg

    def parse_string(
        self,
        content: str,
        path: str | os.PathLike = "",
        ext_vars: dict | None = None,
        env: bool | None = None,
        defaults: bool = True,
        **kwargs,
    ) -> Namespace:
        """Parses configuration given as a string.

        Args:
            content: The configuration content.
            path: Optional path to original config path, just for error printing.
            ext_vars: Optional external variables used for parsing jsonnet.
            env: Whether to merge with the parsed environment, ``None`` to use the parser's default.
            defaults: Whether to merge with the parser's defaults.

        Returns:
            A config object with all parsed values.

        Raises:
            ArgumentError: If the parsing fails and ``exit_on_error=False``.
        """
        skip_validation, fail_no_subcommand = get_private_kwargs(
            kwargs, _skip_validation=False, _fail_no_subcommand=True
        )

        try:
            with parser_context(load_value_mode=self.parser_mode):
                cfg = self._load_config_parser_mode(content, path, ext_vars, previous_config.get())

            if defaults or env:
                cfg_base = self._parse_defaults_and_environ(defaults, env)
                cfg = merge_config(self, cfg, cfg_base)

            parsed_cfg = self._parse_common(
                cfg=cfg,
                env=env,
                defaults=defaults,
                skip_validation=skip_validation,
                fail_no_subcommand=fail_no_subcommand,
            )

        except (TypeError, KeyError) as ex:
            self.error(str(ex), ex)

        self._logger.debug("Parsed %s string: %s", self.parser_mode, content)
        return parsed_cfg

    def _load_config_parser_mode(
        self,
        content: str,
        path: str | os.PathLike = "",
        ext_vars: dict | None = None,
        prev_cfg: Namespace | None = None,
    ) -> Namespace:
        """Loads a configuration string into a namespace.

        Args:
            content: The configuration content.
            path: Optional path to original config path, just for error printing.
            ext_vars: Optional external variables used for parsing jsonnet.

        Raises:
            TypeError: If there is an invalid value according to the parser.
        """
        try:
            cfg_dict = load_value(content, path=path, ext_vars=ext_vars)
        except get_loader_exceptions() as ex:
            raise TypeError(f"Problems parsing config: {ex}") from ex
        if not isinstance(cfg_dict, dict):
            raise TypeError(f"Unexpected config: {content}")
        return self._apply_actions(cfg_dict, prev_cfg=prev_cfg)

    ## Methods for adding to the parser ##

    add_argument = ActionsContainer.add_argument
    add_argument_group = ActionsContainer.add_argument_group
    add_function_arguments = SignatureArguments.add_function_arguments
    add_method_arguments = SignatureArguments.add_method_arguments
    add_class_arguments = SignatureArguments.add_class_arguments
    add_subclass_arguments = SignatureArguments.add_subclass_arguments
    link_arguments = ArgumentLinking.link_arguments

    def add_subcommands(self, required: bool = True, dest: str = "subcommand", **kwargs) -> ActionSubCommands:
        """Adds subcommand parsers to the ArgumentParser.

        The aim is the same as `argparse.ArgumentParser.add_subparsers
        <https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_subparsers>`_
        the difference being that dest by default is ``subcommand`` and the parsed
        values of the subcommand are stored in a nested namespace using the
        subcommand's name as base key.

        Args:
            required: Whether the subcommand must be provided.
            dest: Destination key where the chosen subcommand name is stored.
            **kwargs: All options that `argparse.ArgumentParser.add_subparsers
                <https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser.add_subparsers>`_ accepts.
        """
        if "description" not in kwargs:
            kwargs["description"] = "For more details of each subcommand, add it as an argument followed by --help."
        default_config_files = self.default_config_files
        self.default_config_files = []
        subcommands: ActionSubCommands = super().add_subparsers(dest=dest, **kwargs)  # type: ignore[assignment]
        self.default_config_files = default_config_files
        if required:
            set_required(self, subcommands)
        subcommands.parent_parser = self
        subcommands.env_prefix = get_env_var(self)
        self._subcommands_action = subcommands
        return subcommands

    ## Methods for serializing config objects ##

    def dump(
        self,
        namespace: Namespace,
        format: str = "parser_mode",
        skip_unset: bool = True,
        skip_default: bool = False,
        skip_validation: bool = False,
        with_comments: bool = False,
        skip_link_targets: bool = True,
    ) -> str:
        """Generates a serialized string for the given configuration object.

        Args:
            namespace: The configuration object to dump.
            format: The output format: ``yaml``, ``json``, ``json_indented``, ``toml``, ``parser_mode`` or ones added
                via :func:`.set_dumper`.
            skip_unset: Whether to exclude entries whose value is the configured None/Unset value.
            skip_default: Whether to exclude entries whose value is the same as the default.
            skip_validation: Whether to skip parser checking.
            with_comments: Whether to add help content as comments. Currently only supported for ``format="yaml"``.
            skip_link_targets: Whether to exclude link targets.

        Returns:
            The configuration in the chosen format.

        Raises:
            TypeError: If any of the values of namespace is invalid according to the parser.
        """
        check_valid_dump_format(format)

        cfg = namespace.clone(with_meta=False)

        with parser_context(load_value_mode=self.parser_mode):
            if not skip_validation:
                self.validate(cfg)

            if skip_link_targets:
                ActionLink.strip_link_target_keys(self, cfg)

            dump_kwargs = {"skip_validation": skip_validation, "skip_unset": skip_unset}
            self._dump_cleanup_actions(cfg, self._actions, dump_kwargs)
            cfg = subclasses_disabled_remove_class_path(cfg)

            cfg_dict = cfg.as_dict()

            if skip_default:
                defaults = self.get_defaults(skip_validation=True)
                ActionLink.strip_link_target_keys(self, defaults)
                self._dump_cleanup_actions(defaults, self._actions, {"skip_validation": True, "skip_unset": skip_unset})
                self._dump_delete_default_entries(cfg_dict, defaults.as_dict())

        with parser_context(parent_parser=self):
            return dump_using_format(self, cfg_dict, dump_format=format, with_comments=with_comments)

    def _dump_cleanup_actions(self, cfg, actions, dump_kwargs, prefix=""):
        skip_unset = dump_kwargs["skip_unset"]
        unset_sentinel = get_parsing_setting("unset_sentinel")
        for action in filter_non_parsing_actions(actions):
            action_dest = prefix + action.dest
            if (
                (action.help == argparse.SUPPRESS and not isinstance(action, _ActionConfigLoad))
                or isinstance(action, ActionConfigFile)
                or (skip_unset and action_dest in cfg and cfg[action_dest] is unset_sentinel)
            ):
                cfg.pop(action_dest, None)
            elif isinstance(action, ActionSubCommands):
                cfg.pop(action_dest, None)
                for key, subparser in action.choices.items():
                    self._dump_cleanup_actions(cfg, subparser._actions, dump_kwargs, prefix=prefix + key + ".")
            elif isinstance(action, ActionLink):
                action = action.target[1]
            if isinstance(action, ActionTypeHint):
                value = cfg.get(action_dest)
                if action_dest in cfg and value is not unset_sentinel:
                    with parser_context(parent_parser=self, lenient_check=True):
                        if dump_kwargs.get("skip_validation"):
                            with suppress(ValueError):
                                value = action.serialize(value, dump_kwargs=dump_kwargs)
                        else:
                            value = action.serialize(value, dump_kwargs=dump_kwargs)
                    cfg.update(value, action_dest)

    def _dump_delete_default_entries(self, subcfg, subdefaults):
        for key in list(subcfg.keys()):
            if key in subdefaults:
                val = subcfg[key]
                default = subdefaults[key]
                class_object_val = None
                if is_subclass_spec(val):
                    if val["class_path"] != default.get("class_path"):
                        with parser_context(parent_parser=self):
                            parser = ActionTypeHint.get_class_parser(val["class_path"])
                        default = {"init_args": parser.get_defaults().as_dict()}
                    class_object_val = val
                    val = val.get("init_args")
                    default = default.get("init_args")
                if val == default:
                    del subcfg[key]
                elif isinstance(val, dict) and isinstance(default, dict):
                    self._dump_delete_default_entries(val, default)
                    if class_object_val and class_object_val.get("init_args") == {}:
                        del class_object_val["init_args"]

    def save(
        self,
        namespace: Namespace,
        path: str | os.PathLike,
        format: str = "parser_mode",
        skip_unset: bool = True,
        skip_validation: bool = False,
        overwrite: bool = False,
        multifile: bool = True,
        branch: str | None = None,
    ) -> None:
        """Writes to file(s) the given configuration object using the chosen format.

        Args:
            namespace: The configuration object to save.
            path: Path to the location where to save config.
            format: The output format: ``yaml``, ``json``, ``json_indented``, ``parser_mode`` or ones added via
                :func:`.set_dumper`.
            skip_unset: Whether to exclude entries whose value is the configured None/Unset value.
            skip_validation: Whether to skip parser checking.
            overwrite: Whether to overwrite existing files.
            multifile: Whether to save multiple config files by using the ``__path__`` metas.

        Raises:
            TypeError: If any of the values of namespace is invalid according to the parser.
        """
        check_valid_dump_format(format)

        def check_overwrite(path):
            if not overwrite and os.path.isfile(path.absolute):
                raise ValueError(f"Refusing to overwrite existing file: {path.absolute}")

        dump_kwargs: dict = {"format": format, "skip_unset": skip_unset, "skip_validation": skip_validation}

        if fsspec_support:
            try:
                path_sw = Path(path, mode="sw")
            except TypeError:
                pass
            else:
                if path_sw.is_fsspec:
                    if multifile:
                        raise NotImplementedError(f"multifile=True not supported for fsspec paths: {path}")
                    fsspec = import_fsspec("ArgumentParser.save")
                    with fsspec.open(path, "w") as f:
                        f.write(self.dump(namespace, **dump_kwargs))
                    return

        path_fc = Path(path, mode="fc")
        check_overwrite(path_fc)

        if not multifile:
            with open(path_fc.absolute, "w") as f:
                f.write(self.dump(namespace, **dump_kwargs))

        else:
            cfg = namespace.clone()

            if not skip_validation:
                with parser_context(load_value_mode=self.parser_mode):
                    self.validate(cfg.clone(with_meta=False), branch=branch)

            ActionLink.strip_link_target_keys(self, cfg)

            def is_path_action(key):
                action = find_action(self, key)
                return isinstance(action, (ActionJsonSchema, ActionJsonnet, ActionTypeHint, _ActionConfigLoad))

            def save_path(val):
                val_path = Path(os.path.basename(val["__path__"].absolute), mode="fc")
                check_overwrite(val_path)
                val_out = remove_meta(val)
                if isinstance(val, Namespace):
                    val_out = val_out.as_dict()
                if "__orig__" in val:
                    val_str = val["__orig__"]
                else:
                    is_json = str(val_path).lower().endswith(".json")
                    val_str = dump_using_format(self, val_out, "json_indented" if is_json else format)
                with open(val_path.absolute, "w") as f:
                    f.write(val_str)
                return os.path.basename(val_path)

            def save_paths(cfg):
                for key in get_non_meta_sorted_keys(cfg):
                    val = cfg[key]
                    if isinstance(val, (Namespace, dict)) and "__path__" in val:
                        if is_path_action(key):
                            cfg[key] = save_path(val)
                    elif isinstance(val, list):
                        if is_path_action(key):
                            for num, item in enumerate(val):
                                if isinstance(item, (Namespace, dict)) and "__path__" in item:
                                    val[num] = save_path(item)
                    elif isinstance(val, Path) and key in self.save_path_content and "r" in val.mode:
                        val_path = Path(os.path.basename(val.absolute), mode="fc")
                        check_overwrite(val_path)
                        with open(val_path.absolute, "w") as f:
                            f.write(val.read_text())
                        cfg[key] = type(val)(str(val_path))

            with change_to_path_dir(path_fc), parser_context(parent_parser=self):
                save_paths(cfg)
            dump_kwargs["skip_validation"] = True
            with open(path_fc.absolute, "w") as f:
                f.write(self.dump(cfg, **dump_kwargs))

    ## Methods related to defaults ##

    def _get_default_config_files(self) -> list[Path]:
        if getattr(self, "_inner_parser", False):
            return []

        default_config_files = []

        for pattern in self.default_config_files:
            default_config_files += sorted(glob.glob(os.path.expanduser(pattern)))

        if len(default_config_files) > 0:
            with suppress(TypeError):
                return [Path(v, mode=_get_config_read_mode()) for v in default_config_files]
        return []

    def get_default(self, dest: str) -> Any:
        """Gets a single default value for the given destination key.

        Args:
            dest: Destination key from which to get the default.

        Raises:
            KeyError: If key or its default not defined in the parser.
        """
        action, _ = find_parent_action_and_subcommand(self, dest)
        if action is None or dest != action.dest:
            raise NSKeyError(f'No action for key "{dest}" to get its default.')

        def check_suppressed_default():
            if action.default == argparse.SUPPRESS:
                raise NSKeyError(f'Action for key "{dest}" does not specify a default.')

        if not self._get_default_config_files():
            check_suppressed_default()
            return action.default

        defaults = self.get_defaults()
        if action.dest not in defaults:
            check_suppressed_default()
        return defaults.get(action.dest)

    def get_defaults(self, skip_validation: bool = False) -> Namespace:
        """Returns a namespace with all default values.

        Args:
            skip_validation: Whether to skip validation of defaults.

        Returns:
            An object with all default values as attributes.
        """
        cfg = Namespace()
        for action in filter_non_parsing_actions(self._actions):
            if (
                action.default != argparse.SUPPRESS
                and action.dest != argparse.SUPPRESS
                and not isinstance(action.default, UnknownDefault)
            ):
                default = recreate_branches(action.default)
                cfg[action.dest] = default

        self._logger.debug("Loaded parser defaults: %s", cfg)

        default_config_files = self._get_default_config_files()
        for default_config_file in default_config_files:
            with (
                load_config_path_context(default_config_file),
                change_to_path_dir(default_config_file),
                parser_context(parent_parser=self, parsing_defaults=True),
            ):
                default_config_file_content = default_config_file.read_text()
                if not default_config_file_content.strip():
                    continue
                cfg_file = self._load_config_parser_mode(default_config_file_content, prev_cfg=cfg)
                cfg = merge_config(self, cfg_file, cfg)
                try:
                    with _ActionPrintConfig.skip_print_config():
                        cfg = self._parse_common(
                            cfg=cfg,
                            env=False,
                            defaults=False,
                            skip_validation=skip_validation,
                            skip_required=True,
                            fail_no_subcommand=False,
                        )
                except (TypeError, KeyError, argparse.ArgumentError) as ex:
                    raise argument_error(
                        f"Problem in default config file '{default_config_file}': {ex.args[0]}",
                        default_config_file=str(default_config_file),
                    ) from ex
            meta = cfg.get("__default_config__")
            if isinstance(meta, list):
                meta.append(default_config_file)
            elif isinstance(meta, Path):
                cfg["__default_config__"] = [meta, default_config_file]
            else:
                cfg["__default_config__"] = default_config_file
            self._logger.debug("Parsed default configuration from path: %s", default_config_file)

        with parser_context(validating_defaults=True):
            ActionTypeHint.add_sub_defaults(self, cfg)

        return cfg

    set_defaults = ActionsContainer.set_defaults

    ## Completion script methods ##

    def _raise_invalidated_by_completion_script(self, *args, **kwargs) -> NoReturn:
        raise ValueError(
            "Parser instance was invalidated by get_completion_script() and cannot be reused. "
            "Create a new parser instance."
        )

    def _invalidate_by_completion_script(self) -> None:
        for name in dir(self):
            if name.startswith("_"):
                continue
            static_attr = inspect.getattr_static(self, name, None)
            if inspect.isroutine(static_attr):
                attr = getattr(self, name, None)
                if inspect.ismethod(attr):
                    setattr(self, name, self._raise_invalidated_by_completion_script)

    def get_completion_script(self, completion_type: str, **kwargs) -> str:
        """Returns shell completion script for a completion type."""
        completion_script = get_completion_script_internal(self, completion_type, **kwargs)
        self._invalidate_by_completion_script()
        return completion_script

    ## Other methods ##

    def error(self, message: str, ex: Exception | None = None) -> NoReturn:
        """Logs error message if a logger is set and exits or raises an :class:`ArgumentError`."""
        self._logger.error(message)
        if not self.exit_on_error:
            raise argument_error(message) from ex
        elif debug_mode_active():
            self._logger.debug("Debug enabled, thus raising exception instead of exit.")
            raise argument_error(message) from ex

        parser = getattr(ex, "subcommand_parser", None) or self
        if getattr(ex, "default_config_file", None):
            parser.default_config_files = []
        parser.print_usage(sys.stderr)

        help_action = next((a for a in parser._actions if isinstance(a, argparse._HelpAction)), None)
        if help_action:
            prog = parser.prog.replace(" [options]", "")
            sys.stderr.write(f"tip: For details of accepted options run: {prog} {help_action.option_strings[-1]}\n")

        sys.stderr.write(f"error: {message}\n")
        self.exit(2)

    def validate(
        self,
        namespace: Namespace,
        skip_unset: bool = True,
        skip_required: bool = False,
        branch: str | None = None,
        **kwargs,
    ) -> None:
        """Checks that the content of a given configuration object conforms with the parser.

        Args:
            namespace: The configuration object to check.
            skip_unset: Whether to skip checking of values that are the configured None/Unset value.
            skip_required: Whether to skip checking required arguments.
            branch: Base key in case cfg corresponds only to a branch.

        Raises:
            TypeError: If any of the values are not valid.
            KeyError: If a key in cfg is not defined in the parser.
        """
        prefix = get_private_kwargs(kwargs, _prefix="")
        cfg = ccfg = namespace.clone()
        if isinstance(branch, str):
            branch_cfg = cfg
            cfg = Namespace()
            cfg[branch] = branch_cfg

        def check_required(cfg, parser, prefix):
            missing = []
            for reqkey in iter_required_keys(parser):
                try:
                    val = cfg[reqkey]
                    if val is get_parsing_setting("unset_sentinel"):
                        raise TypeError
                except (KeyError, TypeError):
                    missing.append(f"{prefix}{reqkey}")
            subcommand, subparser = get_subcommand(parser, cfg, fail_no_subcommand=False)
            if subcommand is not None and subparser is not None:
                missing.extend(check_required(cfg.get(subcommand), subparser, prefix + subcommand + "."))
            if prefix == "" and missing:
                raise TypeError(f"the following arguments are required: {', '.join(missing)}")
            return missing

        def check_values(cfg):
            sorted_keys = {k: find_action(self, k) for k in get_non_meta_sorted_keys(cfg)}
            for key, action in sorted_keys.items():
                parent_action = None
                if action is None:
                    if is_branch_key(self, key):
                        continue
                    parent_action, subcommand = find_parent_action_and_subcommand(self, key, exclude=_ActionConfigLoad)
                    if parent_action:
                        parent_key = subcommand + "." + parent_action.dest if subcommand else parent_action.dest
                        if key.startswith(parent_key + ".") and sorted_keys.get(parent_key) is parent_action:
                            # only check action once with entire value
                            continue
                val = cfg[key]
                if action is not None:
                    if (val is get_parsing_setting("unset_sentinel") and skip_unset) or lenient_check.get():
                        continue
                    try:
                        self._check_value_key(action, val, key, ccfg)
                    except TypeError as ex:
                        if not (val == {} and ActionTypeHint.is_subclass_typehint(action)):
                            raise ex
                else:
                    if isinstance(parent_action, ActionSubCommands) and "." in key:
                        subcommand, subkey = split_key_root(key)
                        ex = NSKeyError(f"Subcommand '{subcommand}' does not accept option '{subkey}'")
                        ex.subcommand_parser = parent_action._name_parser_map[subcommand]
                        raise ex
                    group_key = next((g for g in self.groups if key.startswith(g + ".")), None)
                    if group_key:
                        subkey = key[len(group_key) + 1 :]
                        raise NSKeyError(f"Group '{group_key}' does not accept option '{subkey}'")
                    if self._subcommands_action:
                        if cfg.get(self._subcommands_action.dest):
                            subcommand = f"'{cfg[self._subcommands_action.dest]}'"
                        else:
                            subcommand = f"{{{list(self._subcommands_action.choices)[0]},...}}"
                        raise NSKeyError(f"Option '{key}' is not accepted before subcommand {subcommand}")
                    raise NSKeyError(f"Option '{key}' is not accepted")

        with parser_context(load_value_mode=self.parser_mode):
            check_values(cfg)
        if not skip_required and not lenient_check.get():
            check_required(cfg, self, prefix)

    instantiate = InstantiateMethod.instantiate

    def strip_unknown(self, namespace: Namespace) -> Namespace:
        """Removes all unknown keys from a configuration object.

        Args:
            namespace: The configuration object to strip.

        Returns:
            The stripped configuration object.
        """
        cfg = namespace.clone()

        del_keys = []
        for key in cfg.keys():
            if find_action(self, key) is None and not is_meta_key(key):
                del_keys.append(key)

        for key in del_keys:
            del cfg[key]

        return cfg

    def get_config_files(self, namespace: Namespace) -> list[str]:
        """Returns a list of loaded config file paths.

        Args:
            namespace: The configuration object.

        Returns:
            Paths to loaded config files.
        """
        cfg_files = []
        if "__default_config__" in namespace:
            cfg_files.append(namespace["__default_config__"])
        unset_sentinel = get_parsing_setting("unset_sentinel")
        for action in filter_non_parsing_actions(self._actions):
            if (
                isinstance(action, ActionConfigFile)
                and action.dest in namespace
                and namespace[action.dest] is not unset_sentinel
            ):
                cfg_files.extend(p for p in namespace[action.dest] if p is not None)
        return cfg_files

    def format_help(self) -> str:
        defaults = None
        if len(self._default_config_files) > 0:
            note = "no existing default config file found."
            try:
                defaults = self.get_defaults()
                if "__default_config__" in defaults:
                    config_files = defaults["__default_config__"]
                    if isinstance(config_files, list):
                        config_files = [str(x) for x in config_files]
                    note = f"default values below are the ones overridden by the contents of: {config_files}"
            except argparse.ArgumentError as ex:
                note = f"tried getting defaults considering default_config_files but failed due to: {ex}"
            group = self._default_config_files_group
            group.description = f"{self._default_config_files}, Note: {note}"
        with restore_suppressed_required(), parser_context(parent_parser=self, defaults_cache=defaults):
            help_str = super().format_help()
        return help_str

    def print_usage(self, *args, **kwargs) -> None:
        with parser_context(parent_parser=self):
            return super().print_usage(*args, **kwargs)

    def _apply_actions(
        self,
        cfg: Namespace | dict[str, Any],
        parent_key: str = "",
        prev_cfg: Namespace | None = None,
        skip_fn: Callable[[Any], bool] | None = None,
    ) -> Namespace:
        """Runs _check_value_key on actions present in config."""
        if isinstance(cfg, dict):
            cfg = Namespace(cfg)
        if parent_key:
            cfg_branch = cfg
            cfg = Namespace()
            cfg[parent_key] = cfg_branch
            keys = [parent_key + "." + k for k in cfg_branch.keys(branches=True, nested=False)]
        else:
            keys = list(cfg.keys(branches=True, nested=False))

        if prev_cfg:
            prev_cfg = prev_cfg.clone()
        else:
            prev_cfg = Namespace()

        config_keys: set[str] = set()
        num = 0
        while num < len(keys):
            key = keys[num]
            exclude = _ActionConfigLoad if key in config_keys else None
            action, subcommand = find_action_and_subcommand(self, key, exclude=exclude)

            if isinstance(action, ActionJsonnet):
                ext_vars_key = action._ext_vars
                if ext_vars_key and ext_vars_key not in keys[:num]:
                    keys = keys[:num] + [ext_vars_key] + [k for k in keys[num:] if k != ext_vars_key]
                    continue

            num += 1

            if action is None or isinstance(action, ActionSubCommands):
                value = cfg[key]
                if isinstance(value, dict):
                    value = Namespace(value)
                if isinstance(value, Namespace):
                    new_keys = value.keys(branches=True, nested=False)
                    keys += [key + "." + k for k in new_keys if key + "." + k not in keys]
                cfg[key] = value
                continue

            action_dest = action.dest if subcommand is None else subcommand + "." + action.dest
            append = False
            if action_dest not in cfg and key.endswith("+"):
                append = True
                cfg[action_dest] = cfg.pop(key)
            value = cfg[action_dest]
            if skip_fn and skip_fn(value):
                continue
            with parser_context(parent_parser=self, lenient_check=True):
                value = self._check_value_key(action, value, action_dest, prev_cfg, append=append)
            if isinstance(action, _ActionConfigLoad):
                config_keys.add(action_dest)
                keys.append(action_dest)
            elif isinstance(action, ActionConfigFile):
                if isinstance(value, str):
                    cfg.pop(action_dest)
                    preserve = Namespace({k: cfg[k] for k in keys[num:]})
                    ActionConfigFile.apply_config(self, cfg, action_dest, value)
                    cfg.update(preserve)
                    continue
            elif getattr(action, "jsonnet_ext_vars", False):
                prev_cfg[action_dest] = value
            cfg[action_dest] = value
        return cfg[parent_key] if parent_key else cfg

    def _check_value_key(
        self, action: argparse.Action, value: Any, key: str, cfg: Namespace | None, append: bool = False
    ) -> Any:
        """Checks the value for a given action.

        Args:
            action: The action used for parsing.
            value: The value to parse.
            key: The configuration key.

        Raises:
            TypeError: If the value is not valid.
        """
        unset_sentinel = get_parsing_setting("unset_sentinel")
        if value is unset_sentinel and lenient_check.get():
            return value
        is_subcommand = isinstance(action, ActionSubCommands)
        if is_subcommand and action.choices:
            leaf_key = split_key_leaf(key)[-1]
            if leaf_key == action.dest:
                return value
            subparser = action._name_parser_map[leaf_key]  # type: ignore[attr-defined]
            subparser.validate(value, _prefix=key + ".")
        elif isinstance(action, _ActionConfigLoad):
            if isinstance(value, str):
                value = action.check_type(value, self)
        elif hasattr(action, "_check_type"):
            with parser_context(parent_parser=self):
                value = action._check_type_(value, cfg=cfg, append=append, mode=self.parser_mode)  # type: ignore[attr-defined]
        elif action.type is not None:
            try:
                if action.nargs in {None, "?"} or action.nargs == 0:
                    value = action.type(value)  # type: ignore[operator]
                elif value is not None:
                    for k, v in enumerate(value):
                        value[k] = action.type(v)  # type: ignore[operator]
            except (TypeError, ValueError) as ex:
                raise TypeError(f'Parser key "{key}": {ex}') from ex
        if not is_subcommand and action.choices:
            vals = value if _is_action_value_list(action) else [value]
            assert isinstance(vals, list)
            for val in vals:
                if val not in action.choices:
                    raise TypeError(f'Parser key "{key}": {val!r} not among choices {action.choices}')
        return value

    ## Properties ##

    @property
    def default_config_files(self) -> list[str]:
        """Default config file locations.

        :getter: Returns the current default config file locations.
        :setter: Sets new default config file locations, e.g. ``['~/.config/myapp/*.yaml']``.

        Raises:
            ValueError: If an invalid value is given.
        """
        return self._default_config_files

    @default_config_files.setter
    def default_config_files(self, default_config_files: Sequence[str | os.PathLike] | None):
        if default_config_files is None:
            self._default_config_files = []
        elif isinstance(default_config_files, list) and all(
            isinstance(x, (str, os.PathLike)) for x in default_config_files
        ):
            self._default_config_files = [os.fspath(d) for d in default_config_files]
        else:
            raise ValueError("default_config_files expects None or List[str | os.PathLike].")

        if len(self._default_config_files) > 0:
            if not hasattr(self, "_default_config_files_group"):
                group_title = "default config file locations"
                group_class = getattr(self, "_group_class", ArgumentGroup)
                group = group_class(self, title=group_title)
                self._action_groups = [group] + self._action_groups  # type: ignore[operator]
                self._default_config_files_group = group
        elif hasattr(self, "_default_config_files_group"):
            self._action_groups = [g for g in self._action_groups if g != self._default_config_files_group]
            delattr(self, "_default_config_files_group")

    @property
    def default_env(self) -> bool:
        """Whether by default environment variables parsing is enabled.

        If the ``JSONARGPARSE_DEFAULT_ENV`` environment variable is set to true or
        false, that value will take precedence.

        :getter: Returns the current default environment variables parsing setting.
        :setter: Sets the default environment variables parsing setting.

        Raises:
            ValueError: If an invalid value is given.
        """
        return self._default_env

    @default_env.setter
    def default_env(self, default_env: bool):
        os_default_env = os.getenv("JSONARGPARSE_DEFAULT_ENV", "").lower()
        if os_default_env in {"true", "false"}:
            self._default_env = os_default_env == "true"
        elif isinstance(default_env, bool):
            self._default_env = default_env
        else:
            raise ValueError("default_env expects a boolean.")
        if self._subcommands_action:
            for subparser in self._subcommands_action._name_parser_map.values():
                subparser.default_env = self._default_env

    @property
    def env_prefix(self) -> bool | str:
        """The environment variables prefix property.

        :getter: Returns the current environment variables prefix.
        :setter: Sets the environment variables prefix.

        Raises:
            ValueError: If an invalid value is given.
        """
        return self._env_prefix

    @env_prefix.setter
    def env_prefix(self, env_prefix: bool | str):
        if env_prefix is True:
            env_prefix = os.path.splitext(self.prog)[0]
        elif not isinstance(env_prefix, (bool, str)):
            raise ValueError("env_prefix expects a string or a boolean.")
        self._env_prefix = env_prefix

    @property
    def parser_mode(self) -> str:
        """Mode for parsing config files, ``yaml``, ``json``, ``jsonnet`` or ones added via :func:`.set_loader`.

        :getter: Returns the current parser mode.
        :setter: Sets the parser mode.

        Raises:
            ValueError: If an invalid value is given.
        """
        return self._parser_mode

    @parser_mode.setter
    def parser_mode(self, parser_mode: str):
        accepted = set(loaders).union({"omegaconf", "omegaconf+"})
        if parser_mode not in accepted:
            raise ValueError(f"The only accepted values for parser_mode are {accepted}.")
        if parser_mode == "jsonnet":
            import_jsonnet("parser_mode=jsonnet")
        self._parser_mode = parser_mode
        if self._subcommands_action:
            for subparser in self._subcommands_action._name_parser_map.values():
                subparser.parser_mode = parser_mode

    @property
    def dump_header(self) -> list[str] | None:
        """Header to include as comment when dumping a config object.

        :getter: Returns the current dump header.
        :setter: Sets the dump header.

        Raises:
            ValueError: If an invalid value is given.
        """
        return self._dump_header

    @dump_header.setter
    def dump_header(self, dump_header: list[str] | None):
        if not (
            dump_header is None or (isinstance(dump_header, list) and all(isinstance(x, str) for x in dump_header))
        ):
            raise ValueError("Expected dump_header to be None or a list of strings.")
        self._dump_header = dump_header

    # Not supported methods

    def parse_known_args(self, *args, **kwargs) -> NoReturn:
        """Raises ``NotImplementedError`` since typos in configs would go unnoticed."""
        raise NotImplementedError("parse_known_args not supported because typos in configs would go unnoticed.")

    def add_subparsers(self, *args, **kwargs) -> NoReturn:
        """Raises ``NotImplementedError`` since jsonargparse uses ``add_subcommands``."""
        raise NotImplementedError("In jsonargparse subcommands are added using the add_subcommands method.")
