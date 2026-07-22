Changelog
=========

All notable changes to this project will be documented in this file. Versions
follow `Semantic Versioning <https://semver.org/>`__
(``<major>.<minor>.<patch>``). Backward incompatible (breaking) changes will
only be introduced in major versions with advance notice in the **Deprecated**
section of releases.

The semantic versioning only considers the public API as described in
:ref:`api-ref`. Components not mentioned in :ref:`api-ref` or different import
paths are considered internals and can change in minor and patch releases.


v4.50.1 (unreleased)
--------------------

Fixed
^^^^^
- ``TypeError`` when adding arguments for a class that has a parameter that has
  a default and is annotated with a non-``@runtime_checkable`` ``Protocol`` type
  (`#935 <https://github.com/mauvilsa/jsonargparse/pull/935>`__).


v4.50.0 (2026-07-22)
--------------------

Added
^^^^^
- ``FromConfigMixin.from_config`` with ``config_read_mode_fsspec_enabled=True``
  now supports fsspec config loading including the resolving of relative paths
  (`#918 <https://github.com/mauvilsa/jsonargparse/pull/918>`__).
- Add ``.Unset`` sentinel and ``unset_sentinel`` setting in
  ``set_parsing_settings`` to distinguish between arguments not provided and
  those explicitly set to ``null`` (`#909
  <https://github.com/mauvilsa/jsonargparse/pull/909>`__).

Fixed
^^^^^
- While parsing, internally preserve ``class_path`` for subclass disabled types
  to correctly support defaults from union of dataclasses (`#921
  <https://github.com/mauvilsa/jsonargparse/pull/921>`__).
- Misleading error message for ``parse_optionals_as_positionals=True`` and
  unrecognized non-positional arguments (`#922
  <https://github.com/mauvilsa/jsonargparse/pull/922>`__).
- Fix subclass instance defaults not being converted to dict format when the
  parameter is keyword-only (declared after ``*``) (`#933
  <https://github.com/mauvilsa/jsonargparse/pull/933>`__).
- Signature ``**kwargs: Unpack[TypedDict]`` where the ``TypedDict`` has
  ``total=False`` incorrectly made the non-``Required`` keys required (`#934
  <https://github.com/mauvilsa/jsonargparse/pull/934>`__).
- ``TypedDict`` requiredness of keys not correctly resolved when using
  postponed annotations (``from __future__ import annotations``) together with
  ``Required``/``NotRequired`` or totality-flipping inheritance, affecting both
  ``Unpack`` and ``type=`` cases (`#934
  <https://github.com/mauvilsa/jsonargparse/pull/934>`__).
- ``TypedDict`` keys annotated with types only imported in ``TYPE_CHECKING``
  blocks not being resolved (`#934
  <https://github.com/mauvilsa/jsonargparse/pull/934>`__).

Changed
^^^^^^^
- Drop support for Python 3.9. The minimum supported Python version is now
  3.10 (`#916 <https://github.com/mauvilsa/jsonargparse/pull/916>`__).
- Renamed some parameters in the public API to improve consistency and clarity
  (`#926 <https://github.com/mauvilsa/jsonargparse/pull/926>`__).

Deprecated
^^^^^^^^^^
- ``skip_none`` parameter of ``ArgumentParser``'s ``dump``, ``save``, and
  ``validate`` was deprecated and will be removed in v5.0.0. Use ``skip_unset``
  instead (`#909 <https://github.com/mauvilsa/jsonargparse/pull/909>`__).
- ``skip_null`` flag for ``--print_config`` was deprecated and will be removed
  in v5.0.0. Use ``skip_unset`` instead (`#909
  <https://github.com/mauvilsa/jsonargparse/pull/909>`__).
- Implicit selection of subcommand when multiple subcommand settings available
  is deprecated and will be removed in v5.0.0. Provide an explicit subcommand
  instead (`#923 <https://github.com/mauvilsa/jsonargparse/pull/923>`__).
- ``ArgumentParser.merge_config`` is deprecated and will be removed in v5.0.0.
  There is no replacement since it is considered internal (`#925
  <https://github.com/mauvilsa/jsonargparse/pull/925>`__).
- ``Optional`` type parameters without a default and required parameters
  without a type annotation when using ``fail_untyped=False`` are currently set
  to optional with default ``None``. In v5.0.0 they will be required. Warnings
  visible with ``JSONARGPARSE_DEPRECATION_WARNINGS=all`` (`#930
  <https://github.com/mauvilsa/jsonargparse/pull/930>`__).


v4.49.0 (2026-05-15)
--------------------

Added
^^^^^
- Support ``Deque`` and ``FrozenSet`` in type hints (`#905
  <https://github.com/mauvilsa/jsonargparse/pull/905>`__).

Fixed
^^^^^
- Detect loops in config files that recursively load subconfig files and raise
  an error showing the config chain instead of recursing indefinitely (`#910
  <https://github.com/mauvilsa/jsonargparse/pull/910>`__).

Changed
^^^^^^^
- Docs now reference methods via the public ``ArgumentParser`` class instead of
  internal mixin classes (`#901
  <https://github.com/mauvilsa/jsonargparse/pull/901>`__).
- Cache class parsers to improve performance and reduce test suite runtime
  (`#903 <https://github.com/mauvilsa/jsonargparse/pull/903>`__).

Deprecated
^^^^^^^^^^
- Implicit component discovery in ``auto_cli`` (calling without a ``components``
  argument) was deprecated and will be removed in v5.0.0. Pass components
  explicitly; explicit is better than implicit (`#895
  <https://github.com/mauvilsa/jsonargparse/pull/895>`__).
- ``instantiate_classes`` is deprecated and will be removed in v5.0.0. Instead
  use ``instantiate`` (`#896
  <https://github.com/mauvilsa/jsonargparse/pull/896>`__).
- ``ArgumentParser.add_instantiator`` is deprecated and will be removed in
  v5.0.0. Use the global function ``jsonargparse.add_instantiator`` instead
  (`#899 <https://github.com/mauvilsa/jsonargparse/pull/899>`__).
- ``Namespace.get_sorted_keys`` and ``Namespace.get_value_and_parent`` are
  deprecated and will be removed in v5.0.0. Instead run ``.keys()`` and then
  sort or get the parent and leaf separately. (`#900
  <https://github.com/mauvilsa/jsonargparse/pull/900>`__).
- ``Path.get_content`` is deprecated and will be removed in v5.0.0. Instead use
  ``Path.read_text`` for text and ``Path.open`` for binary content (`#906
  <https://github.com/mauvilsa/jsonargparse/pull/906>`__).
- ``enable_path`` parameter of ``ArgumentParser.add_argument`` was deprecated
  and will be removed in v5.0.0. Use ``sub_configs`` instead, which is
  consistent with the ``sub_configs`` parameter of the signature methods,
  ``ArgumentParser.add_class_arguments`` etc. (`#907
  <https://github.com/mauvilsa/jsonargparse/pull/907>`__).
- ``enable_path`` parameter of ``ActionJsonSchema`` was deprecated and will be
  removed in v5.0.0. Use ``sub_config`` instead (`#907
  <https://github.com/mauvilsa/jsonargparse/pull/907>`__).


v4.48.0 (2026-04-10)
--------------------

Added
^^^^^
- AST resolver now supports nested attribute calls like
  ``module.submodule.function(**kwargs)`` (`#878
  <https://github.com/mauvilsa/jsonargparse/pull/878>`__).
- ``register_type`` now supports ``TypeAliasType`` (python 3.12+) in addition
  to classes, and registered aliases no longer add subclass help actions
  (`#875 <https://github.com/mauvilsa/jsonargparse/pull/875>`__).
- ``add_class_arguments`` skip support for callable return class parameters
  (`#882 <https://github.com/mauvilsa/jsonargparse/pull/882>`__).
- ``FromConfigMixin`` is now an official public API feature
  (`#884 <https://github.com/mauvilsa/jsonargparse/pull/884>`__).

Fixed
^^^^^
- Fix resolving forward references in generic aliases (e.g.
  ``list["ForwardReferenced"]``) when the forward-referenced type is not
  imported in the using module (`#871
  <https://github.com/mauvilsa/jsonargparse/pull/871>`__).
- ``auto_cli`` no longer fails when a single function, a class ``__init__``, or
  a function/class in a list/dict of components has a parameter named
  ``config`` (`#873 <https://github.com/mauvilsa/jsonargparse/pull/873>`__).

Changed
^^^^^^^
- Now all missing required options are listed in the error message (`#876
  <https://github.com/mauvilsa/jsonargparse/pull/876>`__).
- ``class_from_function`` and ``lazy_instance`` are now located in
  ``jsonargparse.typing`` while the previous import locations are kept for
  compatibility (`#877 <https://github.com/mauvilsa/jsonargparse/pull/877>`__).
- Most argparse tests from the Python standard library are run against
  jsonargparse. Also the explicit deviations from argparse are documented (`#881
  <https://github.com/mauvilsa/jsonargparse/pull/881>`__).
- Replace black and yesqa with ruff in pre-commit (`#883
  <https://github.com/mauvilsa/jsonargparse/pull/883>`__).
- Removed ``reconplogger`` integration (`#886
  <https://github.com/mauvilsa/jsonargparse/pull/886>`__).
- Avoid expensive inspect.stack in parse_args path and other optimizations to
  speed up test suite (`#887
  <https://github.com/mauvilsa/jsonargparse/pull/887>`__).
- Rely on ``required`` attributes to improve compatibility with third-party
  argparse extensions (`#890
  <https://github.com/mauvilsa/jsonargparse/pull/890>`__, `#893
  <https://github.com/mauvilsa/jsonargparse/pull/893>`__).


v4.47.0 (2026-03-13)
--------------------

Added
^^^^^
- Improved ``shtab`` bash typehint completions for ``Union`` and ``Literal``:
  choices for unions that also accept open values now require a prefix to be
  completed, and literal booleans/``None`` now complete as ``false``/``true``
  and ``null`` (`#851 <https://github.com/mauvilsa/jsonargparse/pull/851>`__).
- ``auto_cli`` now supports a ``return_instance`` parameter to instantiate class
  components directly instead of exposing methods as subcommands (`#855
  <https://github.com/mauvilsa/jsonargparse/pull/855>`__).
- New ``ArgumentParser.get_completion_script(completion_type)`` public method
  to generate completion scripts programmatically, and new
  ``set_parsing_settings(add_print_completion_argument=...)`` setting and
  ``JSONARGPARSE_ADD_PRINT_COMPLETION_ARGUMENT`` environment variable to opt-in
  automatic addition of ``--print_completion`` when ``shtab`` is installed
  (`#859 <https://github.com/mauvilsa/jsonargparse/pull/859>`__).

Fixed
^^^^^
- Positional arguments with ``nargs="*"`` or ``nargs="?"`` now correctly allow
  default values, matching standard argparse behavior (`#846
  <https://github.com/mauvilsa/jsonargparse/pull/846>`__).
- Parsing of floats with implicit leading zero (e.g. ``-.5``) not working (`#847
  <https://github.com/mauvilsa/jsonargparse/pull/847>`__).
- Subcommand names now correctly take precedence over top-level option strings
  with the same name, fixing a failure during typed sub-default processing
  (`#853 <https://github.com/mauvilsa/jsonargparse/pull/853>`__).
- ``--help`` no longer fails with ``IndexError`` for options without explicit
  help text while keeping ``argparse`` compatibility for ``help=None`` (`#854
  <https://github.com/mauvilsa/jsonargparse/pull/854>`__).
- ``store_true`` and ``store_false`` arguments now parse boolean environment
  variable values as ``true``/``false`` and raise a clear error for invalid
  values (`#858 <https://github.com/mauvilsa/jsonargparse/pull/858>`__).
- Environment variable overrides now correctly take precedence over
  ``default_config_files`` values for subcommands and nested subsubcommands
  (`#862 <https://github.com/mauvilsa/jsonargparse/pull/862>`__).
- ``omegaconf+`` incorrectly applied for ``default_config_files`` (`#865
  <https://github.com/mauvilsa/jsonargparse/pull/865>`__).
- ``ActionSubCommands.add_subcommand()`` missing from API reference
  (`#863 <https://github.com/mauvilsa/jsonargparse/pull/863>`__).

Changed
^^^^^^^
- Tests are no longer installed by default, there is a separate
  ``jsonargparse_tests`` wheel file for that (`#843
  <https://github.com/mauvilsa/jsonargparse/pull/843>`__).
- Adding argument giving both ``type`` and ``action`` is now allowed
  (`#845 <https://github.com/mauvilsa/jsonargparse/pull/845>`__).
- Parsers no longer auto-add ``--print_shtab`` by default. Completion script
  generation now uses ``shtab-*`` completion types, and when
  ``get_completion_script`` is used the parser instance is invalidated for
  further use. A hidden ``--print_shtab`` argument remains to guide users to
  the new opt-in completion setting (`#859
  <https://github.com/mauvilsa/jsonargparse/pull/859>`__).
- ``JSONARGPARSE_DEBUG`` can only be enabled with ``true`` (case-insensitive)
  (`867 <https://github.com/mauvilsa/jsonargparse/pull/867>`__).


v4.46.0 (2026-02-02)
--------------------

Added
^^^^^
- Public interface for enabling/disabling support of type subclasses (`#817
  <https://github.com/mauvilsa/jsonargparse/pull/817>`__).

Fixed
^^^^^
- Choices with an int type not working correctly (`#827
  <https://github.com/mauvilsa/jsonargparse/pull/827>`__).
- Union of dataclasses not discarding parameters on class change (`#833
  <https://github.com/mauvilsa/jsonargparse/pull/833>`__).
- Targets of links applied on parse not being instantiated (`#834
  <https://github.com/mauvilsa/jsonargparse/pull/834>`__).
- Validation of defaults getting stuck for path with ``-`` (stdin) default
  (`#837 <https://github.com/mauvilsa/jsonargparse/pull/837>`__).
- Failure when parsing deeply nested dataclass with a union parent (`#839
  <https://github.com/mauvilsa/jsonargparse/pull/839>`__).


v4.45.0 (2025-12-26)
--------------------

Added
^^^^^
- Signature methods now when given ``sub_configs=True``, list of paths types can
  now receive a file containing a list of paths (`#816
  <https://github.com/mauvilsa/jsonargparse/pull/816>`__).
- ``FromConfigMixin.from_config`` now supports subclasses (`#822
  <https://github.com/mauvilsa/jsonargparse/pull/822>`__).

Fixed
^^^^^
- Dict override syntax to allow standard form: --cfg.dict.key val (`#824
  <https://github.com/mauvilsa/jsonargparse/pull/824>`__).
- Evaluation of postponed annotations for dataclass inheritance across modules
  not working correctly (`#814
  <https://github.com/mauvilsa/jsonargparse/pull/814>`__).
- Getting parameter descriptions from docstrings not working for dataclass
  inheritance (`#815 <https://github.com/mauvilsa/jsonargparse/pull/815>`__).
- ``default_env=True`` conflicting with ``default_config_files`` (`#818
  <https://github.com/mauvilsa/jsonargparse/pull/818>`__).
- ``default_config_files`` with settings for multiple subcommands not working
  correctly (`#819 <https://github.com/mauvilsa/jsonargparse/pull/819>`__).
- ``register_type`` not checking that the given type is a class (`#820
  <https://github.com/mauvilsa/jsonargparse/pull/820>`__).

Changed
^^^^^^^
- List of paths types now show in the help the supported options for providing
  paths like ``'["PATH1",...]' | LIST_OF_PATHS_FILE | -`` (`#816
  <https://github.com/mauvilsa/jsonargparse/pull/816>`__).
- Providing a choice of subcommand in ``default_config_files`` is now an error
  (`#819 <https://github.com/mauvilsa/jsonargparse/pull/819>`__).


v4.44.0 (2025-11-25)
--------------------

Fixed
^^^^^
- Union types with str and default comment-like string incorrectly parsed as a
  stringified exception of an other subtype (`#812
  <https://github.com/mauvilsa/jsonargparse/pull/812>`__).
- ``FromConfigMixin`` not handling correctly required parameters (`#813
  <https://github.com/mauvilsa/jsonargparse/pull/813>`__).

Changed
^^^^^^^
- Improved error messages when not accepted options are given, referencing which
  parser/subcommand the option was given to. Also suggests running ``--help``
  for the corresponding parser/subcommand (`#809
  <https://github.com/mauvilsa/jsonargparse/pull/809>`__).
- The ``yaml_comments`` parameter of ``ArgumentParser.dump`` has been renamed to
  ``with_comments`` to allow future comments support of other formats (`#811
  <https://github.com/mauvilsa/jsonargparse/pull/811>`__).

Deprecated
^^^^^^^^^^
- ``ArgumentParser.default_meta`` property and ``with_meta`` parameter of
  ``ArgumentParser.parse_*`` are deprecated and will be removed in v5.0.0.
  Instead use ``.clone(with_meta=...)`` (`#810
  <https://github.com/mauvilsa/jsonargparse/pull/810>`__).
- The ``yaml_comments`` parameter of ``ArgumentParser.dump`` is deprecated and
  will be removed in v5.0.0. Use ``with_comments`` instead (`#811
  <https://github.com/mauvilsa/jsonargparse/pull/811>`__).


v4.43.0 (2025-11-11)
--------------------

Added
^^^^^
- Non-public experimental mixin class to override init defaults and instantiate
  from config (`#800 <https://github.com/mauvilsa/jsonargparse/pull/800>`__).

Fixed
^^^^^
- Prevent extra environment variables in helptext when default_env=True, for
  version actions and subcommands (`#787
  <https://github.com/mauvilsa/jsonargparse/pull/787>`__).
- ``Union`` with path type and non-path value incorrectly dumped as string
  (`#789 <https://github.com/mauvilsa/jsonargparse/pull/789>`__).
- Misleading error message for invalid value for ``Literal`` strings (`#790
  <https://github.com/mauvilsa/jsonargparse/pull/790>`__).
- Changing ``omegaconf_absolute_to_relative_paths`` not taking effect after
  parsing once (`#805 <https://github.com/mauvilsa/jsonargparse/pull/805>`__).

Changed
^^^^^^^
- ``parse_optionals_as_positionals`` and ``applied_instantiation_links`` no
  longer marked as experimental (`#788
  <https://github.com/mauvilsa/jsonargparse/pull/788>`__).
- Moved location of ``Path`` class from ``jsonargparse`` to
  ``jsonargparse.typing`` (`#792
  <https://github.com/mauvilsa/jsonargparse/pull/792>`__).
- Non-parsing actions now have a common base class to ease identification
  (`#793 <https://github.com/mauvilsa/jsonargparse/pull/793>`__).
- ``jsonargparse.*`` modules now use Python 3.9+ syntax (`#798
  <https://github.com/mauvilsa/jsonargparse/pull/798>`__).

Deprecated
^^^^^^^^^^
- ``Path.__call__`` is deprecated and will be removed in v5.0.0. Use the
  ``absolute`` or ``relative`` properties instead (`#794
  <https://github.com/mauvilsa/jsonargparse/pull/794>`__).
- ``strip_meta`` is deprecated and will be removed in v5.0.0. Instead use
  ``.clone(with_meta=False)`` (`#795
  <https://github.com/mauvilsa/jsonargparse/pull/795>`__).
- ``compose_dataclasses`` is deprecated and will be removed in v5.0.0. There is
  no direct replacement, whoever is interested can copy the code (`#796
  <https://github.com/mauvilsa/jsonargparse/pull/796>`__).
- ``dict_to_namespace`` is deprecated and will be removed in v5.0.0. No
  replacement is provided because blindly converting a dictionary to a namespace
  may not yield the same results as using a parser, which could lead to
  confusion (`#797 <https://github.com/mauvilsa/jsonargparse/pull/797>`__).


v4.42.0 (2025-10-14)
--------------------

Added
^^^^^
- ``set_parsing_settings`` now supports setting ``allow_py_files`` to enable
  stubs resolver searching in ``.py`` files in addition to ``.pyi`` (`#770
  <https://github.com/mauvilsa/jsonargparse/pull/770>`__).
- Experimental support for dataclass inheritance (`#775
  <https://github.com/mauvilsa/jsonargparse/pull/775>`__).
- Experimental support for pydantic ``BaseModel`` subclasses (`#781
  <https://github.com/mauvilsa/jsonargparse/pull/781>`__).
- Argument to print help for dataclasses nested in types, e.g.
  ``Optional[Data]``, ``Union[Data1, Data2]`` (`#783
  <https://github.com/mauvilsa/jsonargparse/pull/783>`__).
- ``set_parsing_settings`` now supports ``omegaconf_absolute_to_relative_paths``
  to enable backward compatibility of ``omegaconf+`` parser mode by converting
  absolute paths to relative in interpolations (`#774
  <https://github.com/mauvilsa/jsonargparse/pull/774>`__).

Fixed
^^^^^
- Stubs resolver in some cases failing with maximum recursion error (`#770
  <https://github.com/mauvilsa/jsonargparse/pull/770>`__).
- ``dataclass`` with default failing when ``validate_defaults=True`` (`#771
  <https://github.com/mauvilsa/jsonargparse/pull/771>`__).
- Misleading error message when a namespace is used in a list comprehension
  (`#772 <https://github.com/mauvilsa/jsonargparse/pull/772>`__).
- ``omegaconf+`` parser mode failing when there are ``inf``, ``-inf`` or ``nan``
  values (`#773 <https://github.com/mauvilsa/jsonargparse/pull/773>`__).
- ``save`` with ``multifile=True`` not saving separate subconfigs for items in a
  list (`#779 <https://github.com/mauvilsa/jsonargparse/pull/779>`__).
- ``omegaconf`` parser mode failing on spawned processes (`#784
  <https://github.com/mauvilsa/jsonargparse/pull/784>`__).


v4.41.0 (2025-09-04)
--------------------

Added
^^^^^
- Support for Python 3.14 (`#753
  <https://github.com/mauvilsa/jsonargparse/pull/753>`__).
- Support callable protocols for instance factory dependency injection (`#758
  <https://github.com/mauvilsa/jsonargparse/pull/758>`__).
- New ``ActionFail`` for arguments that should fail parsing with a given error
  message (`#759 <https://github.com/mauvilsa/jsonargparse/pull/759>`__).
- Experimental ``omegaconf+`` parser mode that supports variable interpolation
  and resolving across configs and command line arguments. Depending on
  community feedback, in v5.0.0 this new mode could replace the current
  ``omegaconf`` mode, introducing a breaking change (`#765
  <https://github.com/mauvilsa/jsonargparse/pull/765>`__).

Fixed
^^^^^
- Improved parameter kind handling for argument requirement determination.
  ``KEYWORD_ONLY`` parameters now correctly use ``--flag`` style (`#756
  <https://github.com/mauvilsa/jsonargparse/pull/756>`__).
- Some deprecations not shown in the API documentation (`#760
  <https://github.com/mauvilsa/jsonargparse/pull/760>`__).
- Environment variable names not shown in help for positional arguments when
  ``default_env`` is true (`#763
  <https://github.com/mauvilsa/jsonargparse/pull/763>`__).
- ``parse_object`` not parsing correctly configs (`#765
  <https://github.com/mauvilsa/jsonargparse/pull/765>`__).

Changed
^^^^^^^
- Removed support for python 3.8 (`#752
  <https://github.com/mauvilsa/jsonargparse/pull/752>`__).
- ``YAML`` comments feature is now implemented in a separate class to allow
  better support for custom help formatters without breaking the comments (`#754
  <https://github.com/mauvilsa/jsonargparse/pull/754>`__).
- Replaced unmaintained optional dependency ``ruyaml`` with ``ruamel.yaml``
  (`#768 <https://github.com/mauvilsa/jsonargparse/pull/768>`__).

Deprecated
^^^^^^^^^^
- ``DefaultHelpFormatter.*_yaml*_comment*`` methods are deprecated and will be
  removed in v5.0.0. This logic has been moved to a new private class
  ``YAMLCommentFormatter``. If deemed necessary, this class might be made public
  in the future (`#754 <https://github.com/mauvilsa/jsonargparse/pull/754>`__).
- The ``ruyaml`` optional dependency is deprecated and will be removed in
  v5.0.0. Instead use the ``ruamel`` optional dependency (`#768
  <https://github.com/mauvilsa/jsonargparse/pull/768>`__).


v4.40.2 (2025-08-06)
--------------------

Fixed
^^^^^
- Subclass defaults incorrectly taken from base class (`#743
  <https://github.com/mauvilsa/jsonargparse/pull/743>`__).
- Linking entire dataclasses on instantiation not working (`#746
  <https://github.com/mauvilsa/jsonargparse/pull/746>`__).
- Introspection of postponed annotations from jax not working (`#749
  <https://github.com/mauvilsa/jsonargparse/pull/749>`__).
- ``without-future-annotations`` test not included in local coverage (`#751
  <https://github.com/mauvilsa/jsonargparse/pull/751>`__).


v4.40.1 (2025-07-24)
--------------------

Fixed
^^^^^
- ``print_shtab`` incorrectly parsed from environment variable (`#726
  <https://github.com/mauvilsa/jsonargparse/pull/726>`__).
- ``adapt_class_type`` used a locally defined `partial_instance` wrapper
  function that is not pickleable (`#728
  <https://github.com/mauvilsa/jsonargparse/pull/728>`__).
- ArgumentParser with dashes incorrectly resolves paths to default values (`#736
  <https://github.com/mauvilsa/jsonargparse/pull/736>`__).
- Fix failing tests due to new version of ``typeshed-client`` (`#740
  <https://github.com/mauvilsa/jsonargparse/pull/740>`__).
- Require new version of ``docstring-parser`` to avoid deprecation warnings
  (`#741 <https://github.com/mauvilsa/jsonargparse/pull/741>`__).


v4.40.0 (2025-05-16)
--------------------

Added
^^^^^
- New ``auto_parser`` function for convenience and more visibility of the
  ``capture_parser`` feature (`#721
  <https://github.com/mauvilsa/jsonargparse/pull/721>`__).

Fixed
^^^^^
- ``set_parsing_settings(validate_defaults=True)`` fails when the parser has a
  config action (`#718 <https://github.com/mauvilsa/jsonargparse/pull/718>`__).
- Regression causing dump/save to fail when ``skip_link_targets=True`` and
  target being an entire required dataclass (`#717
  <https://github.com/mauvilsa/jsonargparse/pull/717>`__).
- ``TypedDict`` values not validated when types are forward references (`#722
  <https://github.com/mauvilsa/jsonargparse/pull/722>`__).
- Stubs-only resolver incorrectly triggered when ``inspect.signature`` available
  leading to missing parameter defaults (`#724
  <https://github.com/mauvilsa/jsonargparse/pull/724>`__).

Changed
^^^^^^^
- Use latest jsonnet release that works on all platforms and python versions
  (`#682 <https://github.com/mauvilsa/jsonargparse/pull/682>`__).

Deprecated
^^^^^^^^^^
- ``LoggerProperty`` is deprecated and will be removed in v5.0.0. There is no
  replacement since jsonargparse is not a logging library. A similar class can
  be found in ``reconplogger`` (`#719
  <https://github.com/mauvilsa/jsonargparse/pull/719>`__).
- ``namespace_to_dict`` is deprecated and will be removed in v5.0.0. Instead use
  ``.clone().as_dict()`` or ``.as_dict()`` (`#720
  <https://github.com/mauvilsa/jsonargparse/pull/720>`__).


v4.39.0 (2025-04-29)
--------------------

Added
^^^^^
- ``shtab`` hint for positionals in bash now includes the argument name (`#699
  <https://github.com/mauvilsa/jsonargparse/pull/699>`__).
- ``shtab`` support for optionals parsed as positionals (`#700
  <https://github.com/mauvilsa/jsonargparse/pull/700>`__).
- ``auto_cli`` now supports class ``@property`` (`#701
  <https://github.com/mauvilsa/jsonargparse/pull/701>`__).
- Resolve parameters completely from stubs when ``inspect.signature`` fails
  (`#698 <https://github.com/mauvilsa/jsonargparse/pull/698>`__).
- Option to enable validation of default values (`#711
  <https://github.com/mauvilsa/jsonargparse/pull/711>`__).
- Experimental support for custom instantiators receiving values applied by
  instantiation links (`#716
  <https://github.com/mauvilsa/jsonargparse/pull/716>`__).

Changed
^^^^^^^
- Untyped parameters with ``None`` default no longer skipped when
  ``fail_untyped=True`` (`#697
  <https://github.com/mauvilsa/jsonargparse/pull/697>`__).
- ``config_read_mode`` and ``docstring_parse`` options can now be set using
  ``set_parsing_settings`` (`#712
  <https://github.com/mauvilsa/jsonargparse/pull/712>`__).

Fixed
^^^^^
- ``ActionParser`` not updating ``dest`` of groups for instantiation (`#707
  <https://github.com/mauvilsa/jsonargparse/pull/707>`__).
- Nested generic dataclasses not working correctly (`#709
  <https://github.com/mauvilsa/jsonargparse/pull/709>`__).
- List append nested in subclass not working (`#710
  <https://github.com/mauvilsa/jsonargparse/pull/710>`__).

Deprecated
^^^^^^^^^^
- ``get_config_read_mode``, ``set_config_read_mode`` and
  ``set_docstring_parse_options`` are deprecated and will be removed in v5.0.0.
  Instead of ``set_config_read_mode`` and ``set_docstring_parse_options`` use
  ``set_parsing_settings``. There will be no replacement for
  ``get_config_read_mode`` since this is considered internal (`#712
  <https://github.com/mauvilsa/jsonargparse/pull/712>`__).


v4.38.0 (2025-03-26)
--------------------

Added
^^^^^
- Support ``shtab`` completion of ``Literal`` types (`#693
  <https://github.com/mauvilsa/jsonargparse/pull/693>`__).
- Support for parsing optionals as positionals (`#692
  <https://github.com/mauvilsa/jsonargparse/pull/692>`__).

Changed
^^^^^^^
- ``validate`` now checks values before required so that errors related to wrong
  level in a config are easier to understand (`#681
  <https://github.com/mauvilsa/jsonargparse/pull/681>`__).
- ``add_argument`` of a positional and providing ``default`` now raises an error
  (`#694 <https://github.com/mauvilsa/jsonargparse/pull/694>`__).

Fixed
^^^^^
- ``add_class_arguments`` with dashes in the ``nested_key`` fail to instantiate
  (`#679 <https://github.com/mauvilsa/jsonargparse/pull/679>`__).
- Regression parsing strings with omegaconf as the parser mode (`#686
  <https://github.com/mauvilsa/jsonargparse/pull/686>`__).
- Help incorrectly showing environment variable name for ``--print_shtab``.
- ``add_argument`` raises error when type is assigned with ``action=None``
  (`#687 <https://github.com/mauvilsa/jsonargparse/pull/687>`__).
- ``shtab`` failing when parser has positional arguments (`#693
  <https://github.com/mauvilsa/jsonargparse/pull/693>`__).


v4.37.0 (2025-02-14)
--------------------

Added
^^^^^
- Experimental support for sub-classing ``ArgumentParser`` to customize
  ``add_argument`` (`#661
  <https://github.com/mauvilsa/jsonargparse/pull/661>`__).

Fixed
^^^^^
- Incorrect instantiation order when instantiation targets share a parent (`#662
  <https://github.com/mauvilsa/jsonargparse/pull/662>`__).
- Pydantic discriminated unions handled incorrectly (`#667
  <https://github.com/mauvilsa/jsonargparse/pull/667>`__).
- Failure when a link target has an undefined parent (`#668
  <https://github.com/mauvilsa/jsonargparse/pull/668>`__).
- Functions that create types now have ``TypeAlias`` return type to avoid mypy
  errors (`#671 <https://github.com/mauvilsa/jsonargparse/pull/671>`__).
- String parsing regressions (`#673
  <https://github.com/mauvilsa/jsonargparse/pull/673>`__, `#674
  <https://github.com/mauvilsa/jsonargparse/pull/674>`__).
- Regression when using old ``CLI`` and inferring components from the local
  context (`#676 <https://github.com/mauvilsa/jsonargparse/pull/676>`__).


v4.36.0 (2025-01-17)
--------------------

Added
^^^^^
- Support without ``pyyaml``, though only an internal refactor prior to eventual
  removal of ``pyyaml`` as a required dependency in v5.0.0 (`#652
  <https://github.com/mauvilsa/jsonargparse/pull/652>`__).
- Support for ``toml`` as config file format (`#660
  <https://github.com/mauvilsa/jsonargparse/pull/660>`__).

Changed
^^^^^^^
- ``jsonargparse.CLI`` renamed to ``jsonargparse.auto_cli`` to follow `PEP 8
  <https://peps.python.org/pep-0008/#function-and-variable-names>`__ functions
  naming convention (`#640
  <https://github.com/mauvilsa/jsonargparse/pull/640>`__).
- ``ArgumentParser.check_config`` renamed to ``validate`` and ``skip_check``
  parameter of ``ArgumentParser.{dump, save, get_defaults}`` renamed to
  ``skip_validation`` (`#639
  <https://github.com/mauvilsa/jsonargparse/pull/639>`__).
- Fail when ``Namespace`` is used as a type to make it clear about being
  unsupported (`#656 <https://github.com/mauvilsa/jsonargparse/pull/656>`__).

Fixed
^^^^^
- Help for ``Protocol`` types not working correctly (`#645
  <https://github.com/mauvilsa/jsonargparse/pull/645>`__).
- Adding ``attrs.define`` dataclasses with nested dataclasses that are marked
  with ``attrs.field`` (such as for a default factory) are not parsed correctly
  (`#643 <https://github.com/mauvilsa/jsonargparse/pull/643>`__).
- Nested dataclass with ``init=False`` not working correctly (`#650
  <https://github.com/mauvilsa/jsonargparse/pull/650>`__).

Deprecated
^^^^^^^^^^
- ``ArgumentParser.check_config`` and ``skip_check`` parameter of
  ``ArgumentParser.{dump, save, get_defaults}`` are deprecated and will be
  removed in v5.0.0, instead use ``validate`` and ``skip_validation`` (`#639
  <https://github.com/mauvilsa/jsonargparse/pull/639>`__).


v4.35.0 (2024-12-16)
--------------------

Added
^^^^^
- Support for ``print config`` argument to reuse the name of the config argument
  by using ``%s`` (`#630 <https://github.com/mauvilsa/jsonargparse/pull/630>`__).

Changed
^^^^^^^
- Argument groups created from dataclass-like that have zero configurable
  arguments no longer adds a config loader (`#634
  <https://github.com/mauvilsa/jsonargparse/pull/634>`__).
- The ``CLASS_PATH_OR_NAME`` for subclass help is now optional and if not given
  the help of the base class is printed (`#628
  <https://github.com/mauvilsa/jsonargparse/pull/628>`__).

Fixed
^^^^^
- Account for change in ``ArgumentParser._parse_known_args`` since Python 3.12.8
  and 3.13.1 (`#644 <https://github.com/mauvilsa/jsonargparse/pull/644>`__).

Deprecated
^^^^^^^^^^
- ``add_dataclass_arguments`` is deprecated and will be removed in v5.0.0.
  Instead use ``add_class_arguments`` (`#634
  <https://github.com/mauvilsa/jsonargparse/pull/634>`__).
- From v5.0.0 the print config argument will by default reuse the name of the
  config argument as ``--print_%s`` instead of being always ``--print_config``
  (`#630 <https://github.com/mauvilsa/jsonargparse/pull/630>`__).


v4.34.1 (2024-12-02)
--------------------

Fixed
^^^^^
- List of dataclass with nested dataclass attribute fails to parse (`#625
  <https://github.com/mauvilsa/jsonargparse/pull/625>`__).
- ``NotRequired`` incorrectly having ``inspect._empty`` as default (`#625
  <https://github.com/mauvilsa/jsonargparse/pull/625>`__).
- Callable protocols failing to parse (`#637
  <https://github.com/mauvilsa/jsonargparse/pull/637>`__).
- Help incorrectly showing protocols in known subclasses (`#638
  <https://github.com/mauvilsa/jsonargparse/pull/638>`__).


v4.34.0 (2024-11-08)
--------------------

Added
^^^^^
- Support for PEP 692, i.e., ``Unpack[TypedDict]`` annotations for ``**kwargs``
  (`#586 <https://github.com/mauvilsa/jsonargparse/pull/586>`__).

Fixed
^^^^^
- Empty tuples are now parsed correctly instead of raising an error (`#592
  <https://github.com/mauvilsa/jsonargparse/pull/592>`__).
- Required and optional ``TypedDict`` keys are now correctly inferred when one
  inherits one ``TypedDict`` from another with different totality (`#597
  <https://github.com/mauvilsa/jsonargparse/pull/597>`__).
- Callables that return class not considering previous values (`#603
  <https://github.com/mauvilsa/jsonargparse/pull/603>`__).
- Custom instantiators not working for nested dependency injection (`#608
  <https://github.com/mauvilsa/jsonargparse/pull/608>`__).
- Failure when resolving forward references from dataclass parameter types
  (`#611 <https://github.com/mauvilsa/jsonargparse/pull/611>`__).
- Fix callable protocol inheritance.
  (`#599 <https://github.com/mauvilsa/jsonargparse/pull/599>`__).

Changed
^^^^^^^
- Callables that return class with class default now normalizes the default to
  a subclass spec with ``class_path`` (`#603
  <https://github.com/mauvilsa/jsonargparse/pull/603>`__).


v4.33.2 (2024-10-07)
--------------------

Fixed
^^^^^
- Fix `parse_argv_item` to address the behavior change in `argparse` since
  Python 3.12.7 (`#591 <https://github.com/mauvilsa/jsonargparse/pull/591>`__).


v4.33.1 (2024-09-26)
--------------------

Fixed
^^^^^
- Use ``jsonnet-sdist`` for python 3.13 to be allowed to push package to pypi
  (`#584 <https://github.com/mauvilsa/jsonargparse/pull/584>`__).


v4.33.0 (2024-09-25)
--------------------

Added
^^^^^
- Support for Python 3.13 (`#554
  <https://github.com/mauvilsa/jsonargparse/pull/554>`__).
- Support for ``NotRequired`` and ``Required`` annotations for ``TypedDict``
  keys (`#571 <https://github.com/mauvilsa/jsonargparse/pull/571>`__).
- ``dataclass`` types now accept ``class_path`` and ``init_args`` as value
  (`#581 <https://github.com/mauvilsa/jsonargparse/pull/581>`__).

Fixed
^^^^^
- Callable type with subclass return not showing the ``--*.help`` option (`#567
  <https://github.com/mauvilsa/jsonargparse/pull/567>`__).
- Forward referenced types not compatible with ``Type`` typehint (`#576
  <https://github.com/mauvilsa/jsonargparse/pull/576>`__).
- Subclass nested in ``Iterable`` makes help fail (`#578
  <https://github.com/mauvilsa/jsonargparse/pull/578>`__).
- ``Literal`` mixing enum values and strings failing to parse (`#580
  <https://github.com/mauvilsa/jsonargparse/pull/580>`__).

Changed
^^^^^^^
- Removed shtab experimental warning (`#561
  <https://github.com/mauvilsa/jsonargparse/pull/561>`__).
- For consistency ``add_subclass_arguments`` now sets default ``None`` instead
  of ``SUPPRESS`` (`#568 <https://github.com/mauvilsa/jsonargparse/pull/568>`__).
- Removed support for python 3.7 (`#583
  <https://github.com/mauvilsa/jsonargparse/pull/583>`__).


v4.32.1 (2024-08-23)
--------------------

Fixed
^^^^^
- ``dict`` types not correctly forwarding previous nested values when parsing
  (`#559 <https://github.com/mauvilsa/jsonargparse/pull/559>`__).
- ``List`` type incorrectly using defaults from previous item (`#560
  <https://github.com/mauvilsa/jsonargparse/pull/560>`__).
- ``--print_shtab`` not adding file completer for ``_ActionConfigLoad`` (`#562
  <https://github.com/mauvilsa/jsonargparse/pull/562>`__).
- ``parser_mode`` not inherited by nested parsers (`#564
  <https://github.com/mauvilsa/jsonargparse/pull/564>`__).


v4.32.0 (2024-07-19)
--------------------

Added
^^^^^
- Support for ``MappingProxyType`` as a type and as default for mapping types
  (`#540 <https://github.com/mauvilsa/jsonargparse/pull/540>`__).
- Support for ``OrderedDict`` as a type (`#545
  <https://github.com/mauvilsa/jsonargparse/pull/545>`__).
- New function ``get_loader`` to get the current loader for a given parser mode
  (`#543 <https://github.com/mauvilsa/jsonargparse/pull/543>`__).

Fixed
^^^^^
- ``dump`` failing when a link target requires serialization and
  ``skip_link_targets=False`` (`#542
  <https://github.com/mauvilsa/jsonargparse/pull/542>`__).
- ``default_config_files`` making parse fail for subcommands and nested subclass
  types (`#549 <https://github.com/mauvilsa/jsonargparse/pull/549>`__).
- Fixes related to transformers ``PreTrainedModel.from_pretrained`` (`#551
  <https://github.com/mauvilsa/jsonargparse/pull/551>`__):

    - Import path of inherited classmethod not resolving correctly (`#548
      <https://github.com/mauvilsa/jsonargparse/pull/548>`__).
    - Resolved parameters leading to multiple values for keyword argument (`#551
      <https://github.com/mauvilsa/jsonargparse/pull/551>`__).
    - Function with return type a class in ``class_path`` in some cases fails
      with unexpected ``instantiate`` parameter error (`#551
      <https://github.com/mauvilsa/jsonargparse/pull/551>`__).
    - Ignore incorrectly resolved ``config_file_name`` parameter for
      transformers model ``from_pretrained`` (`#551
      <https://github.com/mauvilsa/jsonargparse/pull/551>`__).


v4.31.0 (2024-06-27)
--------------------

Added
^^^^^
- Support async functions and methods in ``CLI`` (`#531
  <https://github.com/mauvilsa/jsonargparse/pull/531>`__).
- Support for ``Protocol`` types only accepting exact matching signature of
  public methods (`#526
  <https://github.com/mauvilsa/jsonargparse/pull/526>`__).

Fixed
^^^^^
- Resolving of import paths for some ``torch`` functions not working (`#535
  <https://github.com/mauvilsa/jsonargparse/pull/535>`__).
- ``--print_shtab`` crashing on failure to get signature parameters from one
  class (`#537 <https://github.com/mauvilsa/jsonargparse/pull/537>`__).

Changed
^^^^^^^
- Now ``--*.help`` output shows options without ``init_args`` (`#533
  <https://github.com/mauvilsa/jsonargparse/pull/533>`__).


v4.30.0 (2024-06-18)
--------------------

Added
^^^^^
- Allow adding config argument with ``action="config"`` avoiding need to import
  action class (`#512
  <https://github.com/mauvilsa/jsonargparse/pull/512>`__).
- Allow providing a function with return type a class in ``class_path`` (`#513
  <https://github.com/mauvilsa/jsonargparse/pull/513>`__).
- Automatic ``--print_shtab`` option when ``shtab`` is installed, providing
  completions for many type hints without the need to modify code (`#528
  <https://github.com/mauvilsa/jsonargparse/pull/528>`__).

Fixed
^^^^^
- Parsing incorrectly provides file content when type is a union with a
  subclass, PathLike and string (`#518
  <https://github.com/mauvilsa/jsonargparse/pull/518>`__).
- ``--print_config`` failing in some cases (`#531
  <https://github.com/mauvilsa/jsonargparse/pull/531>`__).
- Callable that returns class not using required parameter default from lambda
  (`#523 <https://github.com/mauvilsa/jsonargparse/pull/523>`__).
- Failing to parse list of dataclasses with nested optional dataclass (`#527
  <https://github.com/mauvilsa/jsonargparse/pull/527>`__).
- List of union of classes not accepted by ``add_subclass_arguments`` in
  ``python>=3.11`` (`#522
  <https://github.com/mauvilsa/jsonargparse/pull/522>`__).
- Optional pydantic model failing to parse with `__pydantic_private__` error
  (`#530 <https://github.com/mauvilsa/jsonargparse/pull/530>`__).


v4.29.0 (2024-05-24)
--------------------

Added
^^^^^
- Support for ``TypedDict`` (`#457
  <https://github.com/mauvilsa/jsonargparse/issues/457>`__).
- Directly providing a dict with parameters or a single parameter to a subclass
  or callable with class return now implicitly tries using the base class as
  ``class_path`` if not abstract (`#505
  <https://github.com/mauvilsa/jsonargparse/pull/505>`__).

Fixed
^^^^^
- Parameter resolving falling back to assumptions resolver for optional
  ``Union`` types (`#498 <https://github.com/mauvilsa/jsonargparse/pull/498>`__).
- Nested parameters failing to parse from command line when value includes
  space (`#499 <https://github.com/mauvilsa/jsonargparse/pull/499>`__).
- ``format_usage()`` not working (`#502
  <https://github.com/mauvilsa/jsonargparse/pull/502>`__).
- Not able to modify init args for callable with class return and default class
  (`#504 <https://github.com/mauvilsa/jsonargparse/pull/504>`__).
- Nested values not validated when type not subclass and nested keys for
  subclass (`#506 <https://github.com/mauvilsa/jsonargparse/pull/506>`__).
- Dataclass with nested optional dataclass and default field factory failing to
  parse (`#508 <https://github.com/mauvilsa/jsonargparse/pull/508>`__).

Changed
^^^^^^^
- When parsing fails due to unexpected key, now there are specific error
  messages for the cases of groups and subcommands (`#506
  <https://github.com/mauvilsa/jsonargparse/pull/506>`__).


v4.28.0 (2024-04-17)
--------------------

Added
^^^^^
- Support for "-" as value for Path class initialization so that user
  can ask to use standard input/output instead of file (`#463
  <https://github.com/mauvilsa/jsonargparse/issues/463>`__).
- Option in ``CLI`` to provide subcommands help when components given in a dict
  (`litgpt#996 comment
  <https://github.com/Lightning-AI/litgpt/issues/996#issuecomment-1996201548>`__).
- `TypeAliasType` support added (`#480
  <https://github.com/mauvilsa/jsonargparse/issues/480>`__).

Fixed
^^^^^
- Account for breaking change in ``argparse.ArgumentParser._parse_optional``
  affecting python ``>=3.11.9`` and ``>=3.12.3`` (`#484
  <https://github.com/mauvilsa/jsonargparse/issues/484>`__).
- ``lazy_instance`` not working for callable classes (`#473 comment
  <https://github.com/mauvilsa/jsonargparse/issues/481#issuecomment-2030932435>`__).
- ``Callable`` type with class return and zero arguments not working
  (`lightning#19574 comment
  <https://github.com/lightning-AI/pytorch-lightning/issues/19574#issuecomment-2002932565>`__).
- Attrs and Pydantic 2 dataclasses with non-init fields fail to instantiate
  (`#480 <https://github.com/mauvilsa/jsonargparse/issues/480>`__).
- Default values/factories for Pydantic 2 dataclasses with `Field` initializers
  are not right (`#480 <https://github.com/mauvilsa/jsonargparse/issues/480>`__).
- `Annotated` fields in dataclass-likes (eg FastAPI types) resolve incorrectly
  (`#480 <https://github.com/mauvilsa/jsonargparse/issues/480>`__).


v4.27.7 (2024-03-21)
--------------------

Fixed
^^^^^
- Regression from `14456c2
  <https://github.com/mauvilsa/jsonargparse/commit/14456c21ff7a11ba420f010d2b21bcfdb14977a2>`__
  that prevented ``**kwargs`` parameter resolving when an ``Optional[Callable]``
  type is used (`#473
  <https://github.com/mauvilsa/jsonargparse/issues/473>`__).


v4.27.6 (2024-03-15)
--------------------

Fixed
^^^^^
- Failure when getting parameters from a class created with
  ``class_from_function`` from a ``classmethod`` without parameter types (`#454
  <https://github.com/mauvilsa/jsonargparse/issues/454>`__).
- Subsubcommand parse failing when ``default_env=True`` (`#465
  <https://github.com/mauvilsa/jsonargparse/issues/465>`__).
- Optional callable that returns a class instance with a lambda default,
  produces an invalid string default.
- dataclass single parameter change incorrectly resetting previous values (`#464
  <https://github.com/mauvilsa/jsonargparse/issues/464>`__).
- Add function signature failing when conditionally calling different functions
  (`#467 <https://github.com/mauvilsa/jsonargparse/issues/467>`__).


v4.27.5 (2024-02-12)
--------------------

Fixed
^^^^^
- Importable class instances fail to parse and serialize (`#446
  <https://github.com/mauvilsa/jsonargparse/issues/446>`__).
- Failure when trying to pickle instances created with ``lazy_instance``.
- Confusing error message when creating a link with a target that is already a
  target of another link.


v4.27.4 (2024-02-01)
--------------------

Fixed
^^^^^
- ``argcomplete`` not working when type and choices given (`#442
  <https://github.com/mauvilsa/jsonargparse/issues/442>`__).
- Confusing error message when ``CLI`` is used with a class that defines a
  ``subcommand`` method (`#430 comment
  <https://github.com/mauvilsa/jsonargparse/issues/430#issuecomment-1903974112>`__).
- ``CLI`` crashes when a method has a ``config`` parameter. Due to redundancy,
  ``--config`` argument should not be added.


v4.27.3 (2024-01-26)
--------------------

Fixed
^^^^^
- Argument links not working for target ``init_args`` in an optional list (`#433
  <https://github.com/mauvilsa/jsonargparse/issues/433>`__).
- Signature parameter default that doesn't match its type failing on
  instantiation and serialization (`lightning#19289 comment
  <https://github.com/Lightning-AI/pytorch-lightning/pull/19289#issuecomment-1902618722>`__).


v4.27.2 (2024-01-18)
--------------------

Fixed
^^^^^
- reconplogger's logger level being unexpectedly overwritten.
- Signature parameter default value that doesn't match its type considered
  invalid (`lightning#19289 comment
  <https://github.com/Lightning-AI/pytorch-lightning/pull/19289#issuecomment-1894063743>`__).


v4.27.1 (2023-11-23)
--------------------

Fixed
^^^^^
- Confusing error message when adding signature parameters that conflict with
  existing arguments.
- Deprecation warnings not printing the correct file and line of code.
- ``sub_configs=True`` not working for callable types that return a class (`#419
  <https://github.com/mauvilsa/jsonargparse/issues/419>`__).


v4.27.0 (2023-11-02)
--------------------

Added
^^^^^
- Support for pydantic's ``SecretStr`` type.
- New ``SecretStr`` type in ``jsonargparse.typing`` to provide secret support
  without additional dependency.

Fixed
^^^^^
- Links applied on parse failing when source is a class with a nested callable.


v4.26.2 (2023-10-26)
--------------------

Fixed
^^^^^
- Failure to parse subclass added via add_argument and required arg as link
  target.
- ``choices`` working incorrectly when ``nargs`` is ``+``, ``*`` or number.
- Unable link two deep level arguments sharing the same root class (`#297
  <https://github.com/mauvilsa/jsonargparse/issues/297>`__).


v4.26.1 (2023-10-23)
--------------------

Fixed
^^^^^
- Failures when choices is a ``dict_keys`` object and value non-hashable.
- AST resolver not using the correct component globals in some cases.


v4.26.0 (2023-10-19)
--------------------

Added
^^^^^
- Support for on parse argument links with target subclasses in a list (`#394
  <https://github.com/mauvilsa/jsonargparse/issues/394>`__, `lightning#18161
  <https://github.com/Lightning-AI/lightning/issues/18161>`__).
- AST resolver now supports some local import cases.

Fixed
^^^^^
- Failures with subcommands and default_config_files when keys are repeated
  (`#160 <https://github.com/mauvilsa/jsonargparse/issues/160>`__).
- Key related errors printing messages within single quotes.
- Choices not validated when value comes from config file (`#404
  <https://github.com/mauvilsa/jsonargparse/issues/404>`__).

Changed
^^^^^^^
- Subclass types no longer allow class instance to be set as default
  (`lightning#18731
  <https://github.com/Lightning-AI/lightning/issues/18731>`__).
- ``JSONARGPARSE_DEBUG`` must now have a non-empty value to enable debug mode.


v4.25.0 (2023-09-25)
--------------------

Added
^^^^^
- Support for user-defined generic types (`#366
  <https://github.com/mauvilsa/jsonargparse/issues/366>`__).
- New function ``extend_base_type`` for easy creation and registering of custom
  types that extend a base type (`#195
  <https://github.com/mauvilsa/jsonargparse/issues/195>`__).
- Support for ``Annotated`` types either ignoring the metadata or using it for
  validation in case of `pydantic types
  <https://docs.pydantic.dev/latest/api/types/>`__ (`#384
  <https://github.com/mauvilsa/jsonargparse/issues/384>`__).
- Support for Python 3.12.

Fixed
^^^^^
- ``--print_config`` fails when parser has shallow links.
- Argument links unnecessarily applied when ``--print_config`` used and parser
  has subcommands (`#311 <https://github.com/mauvilsa/jsonargparse/issues/311>`__).
- Parsing fails when data type is a ``Callable`` with multiple input arguments
  (`#372 <https://github.com/mauvilsa/jsonargparse/issues/372>`__).
- Postponed annotations not working for dataclasses.
- Unsupported pop/get default incorrectly sets default as ``None``
  (`lightning#18616
  <https://github.com/Lightning-AI/lightning/issues/18616>`__).
- Pydantic models and dataclasses not working for ``pydantic>=2.0.0`` (`#361
  <https://github.com/mauvilsa/jsonargparse/issues/361>`__).

Changed
^^^^^^^
- Provide a more informative error message to remind user to select
  and provide a subcommand when a subcommand is required but not
  given (`#371 <https://github.com/mauvilsa/jsonargparse/pull/371>`__).
- Now when an argument link ``compute_fn`` fails, the error message will say
  this (`#311 <https://github.com/mauvilsa/jsonargparse/issues/311>`__).
- ``add_subclass_arguments`` now shows a better error message when an empty
  tuple is given (`lightning#18546
  <https://github.com/Lightning-AI/lightning/issues/18546>`__).
- Document the requirements for creating and using custom types (`#195
  <https://github.com/mauvilsa/jsonargparse/issues/195>`__).
- Parameters with default and without type, now get as type
  ``Union[type(default), Any]``.
- Removed support for python 3.6.


v4.24.1 (2023-09-06)
--------------------

Fixed
^^^^^
- Remove private ``linked_targets`` parameter from API Reference (`#317
  <https://github.com/mauvilsa/jsonargparse/issues/317>`__).
- Dataclass nested in list not setting defaults (`#357
  <https://github.com/mauvilsa/jsonargparse/issues/357>`__).
- AST resolver ``kwargs.pop()`` with conflicting defaults not setting the
  conditional default (`#362
  <https://github.com/mauvilsa/jsonargparse/issues/362>`__).
- ``ActionJsonSchema`` not setting correctly defaults when schema uses
  ``oneOf``.
- Recommended ``print_config`` steps not working when ``default_config_files``
  used due to the config file initially being empty (`#367
  <https://github.com/mauvilsa/jsonargparse/issues/367>`__).


v4.24.0 (2023-08-23)
--------------------

Added
^^^^^
- New option in ``dump`` for including link targets.
- Support ``decimal.Decimal`` as a type.
- ``CLI`` now accepts components as a dict, such that the keys define names of
  the subcommands (`#334
  <https://github.com/mauvilsa/jsonargparse/issues/334>`__).
- Resolve types that use ``TYPE_CHECKING`` blocks (`#337 comment
  <https://github.com/mauvilsa/jsonargparse/issues/337#issuecomment-1665055459>`__).
- Improved resolving of nested forward references in types.
- The ``ext_vars`` for an ``ActionJsonnet`` argument can now have a default.
- New method ``ArgumentParser.add_instantiator`` that enables developers to
  implement custom instantiation (`#170
  <https://github.com/mauvilsa/jsonargparse/issues/170>`__).

Deprecated
^^^^^^^^^^
- ``ActionJsonnetExtVars`` is deprecated and will be removed in v5.0.0. Instead
  use ``type=dict``.


v4.23.1 (2023-08-04)
--------------------

Fixed
^^^^^
- ``save`` fails when a link target is a required parameter nested in a subclass
  (`#332 <https://github.com/mauvilsa/jsonargparse/issues/332>`__).
- ``typing.Literal`` types skipped when typing_extensions is installed
  (`lightning#18184 <https://github.com/Lightning-AI/lightning/pull/18184>`__).
- ``class_from_function`` failing when called on the same function multiple
  times (`lightning#18180
  <https://github.com/Lightning-AI/lightning/issues/18180>`__).
- Prevent showing errors when running ``ps`` on windows.


v4.23.0 (2023-07-27)
--------------------

Added
^^^^^
- Classes created with ``class_from_function`` now have a valid import path
  (`#309 <https://github.com/mauvilsa/jsonargparse/issues/309>`__).

Fixed
^^^^^
- Invalid environment variable names when ``env_prefix`` is derived from
  a ``prog`` containing dashes.
- Pylance unable to resolve types from ``jsonargparse.typing``.
- Inconsistent ``ARG:`` and missing ``ENV:`` in help when ``default_env=True``.
- ``typing.Literal`` types skipped on python 3.9 when typing_extensions is
  installed (`lightning#18125 comment
  <https://github.com/Lightning-AI/lightning/pull/18125#issuecomment-1644797707>`__).

Changed
^^^^^^^
- Subcommands main parser help changes:
    - Set notation of subcommands choices now only included in usage.
    - In subcommands section, now each subcommand is always shown separately,
      including the name, and if available aliases and help.
    - When ``default_env=True`` include subcommand environment variable name.


v4.22.1 (2023-07-07)
--------------------

Fixed
^^^^^
- Parameter without default and type optional incorrectly added as a required
  argument (`#312 <https://github.com/mauvilsa/jsonargparse/issues/312>`__).
- ``class_from_function`` not failing when return annotation is missing.
- ``add_subclass_arguments`` with single base class and no docstring,
  incorrectly shown as tuple in help.
- When all arguments of a group are derived from links, a config load option is
  incorrectly shown in help.
- Printing help fails for parsers that have a link whose target is an argument
  lacking type and help.


v4.22.0 (2023-06-23)
--------------------

Added
^^^^^
- Parameters that receive a path now also accept ``os.PathLike`` type.
- ``class_from_function`` now supports ``func_return`` parameter to specify the
  return type of the function (`lightning-flash#1564 comment
  <https://github.com/Lightning-Universe/lightning-flash/pull/1564#discussion_r1218147330>`__).
- Support for postponed evaluation of annotations PEP `563
  <https://peps.python.org/pep-0563/>`__ ``from __future__ import annotations``
  (`#120 <https://github.com/mauvilsa/jsonargparse/issues/120>`__).
- Backport types in python<=3.9 to support PEP `585
  <https://peps.python.org/pep-0585/>`__ and `604
  <https://peps.python.org/pep-0604/>`__ for postponed evaluation of annotations
  (`#120 <https://github.com/mauvilsa/jsonargparse/issues/120>`__).
- Support for ``range`` as a type.

Fixed
^^^^^
- Regular expressions vulnerable to polynomial runtime due to backtracking.
- ``attrs`` fields with factory default causes parse to fail (`#299
  <https://github.com/mauvilsa/jsonargparse/issues/299>`__).
- Stop subclass dive if you hit bad import (`#304
  <https://github.com/mauvilsa/jsonargparse/issues/304>`__).

Changed
^^^^^^^
- Added ``_`` prefix to module names to be explicit about non-public API.

Deprecated
^^^^^^^^^^
- Importing from original non-public module paths (without ``_`` prefix) now
  gives a ``DeprecationWarning``. From v5.0.0 these imports will fail.


v4.21.2 (2023-06-08)
--------------------

Fixed
^^^^^
- Failure for nested argument in optional dataclass type (`#289
  <https://github.com/mauvilsa/jsonargparse/issues/289>`__).
- Argument links applied on parse silently ignored when the source validation
  fails.


v4.21.1 (2023-05-09)
--------------------

Fixed
^^^^^
- AST resolver not working for dict used in a method when the dict is created
  using the curly braces syntax.
- Failure on multiple deep arguments linked on instantiation (`#275
  <https://github.com/mauvilsa/jsonargparse/issues/275>`__).


v4.21.0 (2023-04-21)
--------------------

Added
^^^^^
- Support for dataclasses nested in a type (`#243
  <https://github.com/mauvilsa/jsonargparse/issues/243>`__).
- Support for pydantic `models <https://docs.pydantic.dev/usage/models/>`__ and
  attrs `define <https://www.attrs.org/en/stable/examples.html>`__ similar to
  dataclasses.
- Support for `pydantic types
  <https://docs.pydantic.dev/usage/types/#pydantic-types>`__.
- Backport type stubs in python<=3.9 to support PEP `585
  <https://peps.python.org/pep-0585/>`__ and `604
  <https://peps.python.org/pep-0604/>`__ syntax.

Fixed
^^^^^
- `str` parameter in subclass incorrectly parsed as dict with implicit `null`
  value (`#262 <https://github.com/mauvilsa/jsonargparse/issues/262>`__).
- Wrong error indentation for subclass in union (`lightning#17254
  <https://github.com/Lightning-AI/lightning/issues/17254>`__).
- ``dataclass`` from pydantic not working (`#100 comment
  <https://github.com/mauvilsa/jsonargparse/issues/100#issuecomment-1408413796>`__).
- ``add_dataclass_arguments`` not forwarding ``sub_configs`` parameter.
- Failure to instantiate nested class group without arguments (`lightning#17263
  <https://github.com/Lightning-AI/lightning/issues/17263>`__).

Changed
^^^^^^^
- Switched from ``setup.cfg`` to ``pyproject.toml`` for configuration.
- Removed ``build_sphinx`` from ``setup.py`` and documented how to build.
- Include enum members in error when invalid value is given
  (`lightning#17247
  <https://github.com/Lightning-AI/lightning/issues/17247>`__).
- The ``signatures`` extras now installs the ``typing-extensions`` package on
  python<=3.9.
- ``CLI`` now when given a class without methods, the class instance is
  returned.

Deprecated
^^^^^^^^^^
- Support for python 3.6 will be removed in v5.0.0. New features added in
  >=4.21.0 releases are not guaranteed to work in python 3.6.


v4.20.1 (2023-03-30)
--------------------

Fixed
^^^^^
- Dump not working for partial callable with return instance
  (`lightning#15340 comment
  <https://github.com/Lightning-AI/lightning/issues/15340#issuecomment-1439203008>`__).
- Allow ``discard_init_args_on_class_path_change`` to handle more nested
  contexts (`#247 <https://github.com/mauvilsa/jsonargparse/issues/247>`__).
- Failure with dataclasses that have field with ``init=False`` (`#252
  <https://github.com/mauvilsa/jsonargparse/issues/252>`__).
- Failure when setting individual dict key values for subclasses and
  ``.init_args.`` is included in argument (`#251
  <https://github.com/mauvilsa/jsonargparse/issues/251>`__).


v4.20.0 (2023-02-20)
--------------------

Added
^^^^^
- ``CLI`` support for callable class instances (`#238
  <https://github.com/mauvilsa/jsonargparse/issues/238>`__).
- ``add_dataclass_arguments`` now supports the ``fail_untyped`` parameter (`#241
  <https://github.com/mauvilsa/jsonargparse/issues/241>`__).

Fixed
^^^^^
- ``add_subcommands`` fails when parser has required argument and default config
  available (`#232 <https://github.com/mauvilsa/jsonargparse/issues/232>`__).

Changed
^^^^^^^
- When parsing fails, now ``argparse.ArgumentError`` is raised instead of
  ``ParserError``.
- Improved error messages when ``fail_untyped=True`` (`#137
  <https://github.com/mauvilsa/jsonargparse/issues/137>`__).
- ``CLI`` no longer uses the module's docstring as main parser description (`#245
  <https://github.com/mauvilsa/jsonargparse/issues/245>`__).

Deprecated
^^^^^^^^^^
- Path ``skip_check`` parameter is deprecated and will be removed in v5.0.0.
  Instead use as type ``str`` or ``os.PathLike``.
- Modifying Path attributes is deprecated. In v5.0.0 they will be properties
  without a setter and two renamed: ``rel_path -> relative`` and
  ``abs_path -> absolute``.
- ``ActionPathList`` is deprecated and will be removed in v5.0.0. Instead use as
  type ``List[<path_type>]`` with ``enable_path=True``.
- ``ArgumentParser.error_handler`` is deprecated and will be removed in v5.0.0.
  Instead use the new exit_on_error parameter from argparse.


v4.19.0 (2022-12-27)
--------------------

Added
^^^^^
- ``CLI`` now supports the ``fail_untyped`` and ``parser_class`` parameters.
- ``bytes`` and ``bytearray`` registered on first use and decodes from standard
  Base64.
- Support getting the import path of variables in modules, e.g.
  ``random.randint``.
- Specific error messages for when an argument link uses as source the target of
  a previous parse link and vice versa (`#208
  <https://github.com/mauvilsa/jsonargparse/issues/208>`__).
- New resolver that identifies parameter types from stub files ``*.pyi``.
- Support for relative paths within remote fsspec/url config files.
- New context manager methods for path types: ``open`` and
  ``relative_path_context``.
- Path types now implement the ``os.PathLike`` protocol.
- New path mode ``cc`` to not require the parent directory to exists but that it
  can be created.
- The parent parser class is now used to create internal parsers (`#171
  <https://github.com/mauvilsa/jsonargparse/issues/171>`__).

Fixed
^^^^^
- List type with empty list default causes failure (`PyLaia#48
  <https://github.com/jpuigcerver/PyLaia/issues/48>`__).
- Pure dataclass instance default being considered as a subclass type.
- Discard ``init_args`` after ``class_path`` change causes error (`#205
  <https://github.com/mauvilsa/jsonargparse/issues/205>`__).
- ``fail_untyped=False`` not propagated to subclass ``--*.help`` actions.
- Issues reported by CodeQL.
- Incorrect value when ``Path`` is cast to ``str`` and ``rel_path`` was changed.
- Argument links with target a subclass mixed with other types not working (`#208
  <https://github.com/mauvilsa/jsonargparse/issues/208>`__).
- Failures when using a sequence type and the default is a tuple.
- Parent parser logger not being forwarded to subcommand and internal parsers.

Changed
^^^^^^^
- Clearer error message for when an argument link targets a subclass and the
  target key does not have ``init_args`` (`lightning#16032
  <https://github.com/Lightning-AI/lightning/issues/16032>`__).
- The ``signatures`` extras now installs the ``typeshed-client`` package.
- ``validators`` package is no longer a dependency.
- Path types are no longer a subclass of ``str``.
- Parsing steps logging now at debug level.
- Discarding ``init_args`` warning changed to log at debug level.
- Removed replacing list instead of append warning.


v4.18.0 (2022-11-29)
--------------------

Added
^^^^^
- AST resolving for defaults with a class instance or a lambda that returns a
  class instance.

Fixed
^^^^^
- ``bool`` values should not be accepted by ``int`` or ``float`` types.
- ``parse_string`` raises ``AttributeError`` when given a simple string.
- Added missing ``return_parser`` deprecation warning when ``CLI`` has
  subcommands.
- Parsing fails for registered types that can't be cast to boolean (`#196
  <https://github.com/mauvilsa/jsonargparse/issues/196>`__).
- List append not working for ``default_config_files`` set in a subcommand
  subparser (`lightning#15256
  <https://github.com/Lightning-AI/lightning/issues/15256>`__).
- Specifying only the class name through command line not working for
  ``Callable`` with class return type.
- ``init_args`` not discarded for nested subclasses provided through command
  line (`lightning#15796
  <https://github.com/Lightning-AI/lightning/issues/15796>`__).
- Unable to set/get values in ``Namespace`` when key is the same as a method
  name.

Changed
^^^^^^^
- ``CLI`` no longer adds ``--config`` and ``--print_config`` if no arguments
  added to subcommand.
- ``CLI`` now uses the component's docstring short description for subparser
  descriptions.
- Slightly nicer type hint unexpected value error messages, in particular less
  redundancy for ``Union`` types.


v4.17.0 (2022-11-11)
--------------------

Added
^^^^^
- AST resolver now ignores if/elif/else code when condition is a global constant
  (`#187 <https://github.com/mauvilsa/jsonargparse/issues/187>`__).
- AST resolver support for conditional ``**kwargs`` use in multiple calls (`#187
  comment
  <https://github.com/mauvilsa/jsonargparse/issues/187#issuecomment-1295141338>`__).

Fixed
^^^^^
- ``str`` type fails to parse value when pyyaml raises ``ConstructorError``
  (`#189 <https://github.com/mauvilsa/jsonargparse/issues/189>`__).
- ``Namespace`` clone should not deepcopy leaf values (`#187
  <https://github.com/mauvilsa/jsonargparse/issues/187>`__).
- ``_ActionHelpClassPath`` actions fail to instantiate when base class uses new
  union type syntax.

Changed
^^^^^^^
- Improved help usage and description for ``--print_config``.
- Registering ``pathlib.Path`` types so that they are not shown as subclass
  types.


v4.16.0 (2022-10-28)
--------------------

Added
^^^^^
- Type ``Any`` now parses and instantiates classes when given dict that follows
  subclass specification (`lightning#15115
  <https://github.com/Lightning-AI/lightning/issues/15115>`__).
- Signature methods now accept skipping a number of positionals.
- Callable type hint with return type a class can now be given a subclass which
  produces a callable that returns an instance of the class.
- Support for Python 3.11.

Fixed
^^^^^
- Fail to import on Python 3.7 when typing_extensions not installed (`#178
  <https://github.com/mauvilsa/jsonargparse/issues/178>`__).
- Crashing when using set typehint with specified dtype (`#183
  <https://github.com/mauvilsa/jsonargparse/issues/183>`__).

Changed
^^^^^^^
- Using ``set_defaults`` on a config argument raises error and suggests to use
  ``default_config_files`` (`lightning#15174
  <https://github.com/Lightning-AI/lightning/issues/15174>`__).
- Trying to add a second config argument to a single parser raises an exception
  (`#169 <https://github.com/mauvilsa/jsonargparse/issues/169>`__).


v4.15.2 (2022-10-20)
--------------------

Fixed
^^^^^
- Regression introduced in `6e7ae6d
  <https://github.com/mauvilsa/jsonargparse/commit/6e7ae6dca41d2bdf081731c042bba9d08b6f228f>`__
  that produced cryptic error message when an invalid argument given (`#172
  <https://github.com/mauvilsa/jsonargparse/issues/172>`__).
- ``default_env`` not forwarded to subcommand parsers, causing environment
  variable names to not be shown in subcommand help (`lightning#12790
  <https://github.com/Lightning-AI/lightning/issues/12790>`__).
- Cannot override Callable ``init_args`` without passing the ``class_path``
  (`#174 <https://github.com/mauvilsa/jsonargparse/issues/174>`__).
- Positional subclass type incorrectly adds subclass help as positional.
- Order of types in ``Union`` not being considered.
- ``str`` type fails to parse values of the form ``^\w+: *``.
- ``parse_object`` does not consider given namespace for previous ``class_path``
  values.


v4.15.1 (2022-10-07)
--------------------

Fixed
^^^^^
- ``compute_fn`` of an argument link applied on parse not given subclass default
  ``init_args`` when loading from config.
- Subclass ``--*.help`` option not available when type is a ``Union`` mixed with
  not subclass types.
- Override of ``dict_kwargs`` items from command line not working.
- Multiple subclass ``init_args`` given through command line not being
  considered (`lightning#15007
  <https://github.com/Lightning-AI/lightning/pull/15007>`__).
- ``Union`` types required all subtypes to be supported when expected to be at
  least one subtype supported (`#168
  <https://github.com/mauvilsa/jsonargparse/issues/168>`__).


v4.15.0 (2022-09-27)
--------------------

Added
^^^^^
- ``set_defaults`` now supports subclass by name and normalization of import path.

Fixed
^^^^^
- Loop variable capture bug pointed out by lgtm.com.
- Issue with discard ``init_args`` when ``class_path`` not a subclass.
- No error shown when arguments given to class group that does not accept
  arguments (`#161 comment
  <https://github.com/mauvilsa/jsonargparse/issues/161#issuecomment-1256973565>`__).
- Incorrect replacement of ``**kwargs`` when ``*args`` present in parameter resolver.
- Override of ``class_path`` not discarding ``init_args`` when loading from
  config file.
- Invalid values given to the ``compute_fn`` of a argument link applied on parse
  without showing an understandable error message.

Changed
^^^^^^^
- Now ``UUID`` and ``timedelta`` types are registered on first use to avoid
  possibly unused imports.
- json/yaml dump sort now defaults to false for all python implementations.
- ``add_class_arguments`` will not add config load option if no added arguments.


v4.14.1 (2022-09-26)
--------------------

Fixed
^^^^^
- Making ``import_docstring_parse`` a deprecated function only for
  pytorch-lightning backward compatibility.


v4.14.0 (2022-09-14)
--------------------

Added
^^^^^
- Support for ``os.PathLike`` as typehint (`#159
  <https://github.com/mauvilsa/jsonargparse/issues/159>`__).
- Also show known subclasses in help for ``Type[<type>]``.
- Support for attribute docstrings (`#150
  <https://github.com/mauvilsa/jsonargparse/issues/150>`__).
- Way to configure parsing docstrings with a single style.

Fixed
^^^^^
- Subclass nested argument incorrectly loaded as subclass config (`#159
  <https://github.com/mauvilsa/jsonargparse/issues/159>`__).
- Append to list not working for ``default_config_files`` in subcommands (`#157
  <https://github.com/mauvilsa/jsonargparse/issues/157>`__).


v4.13.3 (2022-09-06)
--------------------

Fixed
^^^^^
- Failure to parse when subcommand has no options (`#158
  <https://github.com/mauvilsa/jsonargparse/issues/158>`__).
- Optional packages being imported even though not used.
- Append to list not working for ``default_config_files`` (`#157
  <https://github.com/mauvilsa/jsonargparse/issues/157>`__).


v4.13.2 (2022-08-31)
--------------------

Fixed
^^^^^
- Failure to print help when ``object`` used as type hint.
- Failure to parse init args when type hint is union of str and class.
- Handle change of non-existent file exception type in latest fsspec version.


v4.13.1 (2022-08-05)
--------------------

Fixed
^^^^^
- Regression that caused parse to fail when providing ``init_args`` from command
  line and the subclass default set as a dict.


v4.13.0 (2022-08-03)
--------------------

Added
^^^^^
- Support setting through command line individual dict items without replacing
  (`#133 comment
  <https://github.com/mauvilsa/jsonargparse/issues/133#issuecomment-1194305222>`__).
- Support ``super()`` with non-immediate method resolution order parameter (`#153
  <https://github.com/mauvilsa/jsonargparse/issues/153>`__).

Fixed
^^^^^
- Mypy fails to find jsonargparse type hints (`#151
  <https://github.com/mauvilsa/jsonargparse/issues/151>`__).
- For multiple ``dict_kwargs`` command line arguments only the last one was
  kept.
- Positional ``list`` with subtype causing crash (`#154
  <https://github.com/mauvilsa/jsonargparse/issues/154>`__).


v4.12.0 (2022-07-22)
--------------------

Added
^^^^^
- Instantiation links now support multiple sources.
- AST resolver now supports ``cls()`` class instantiation in ``classmethod``
  (`#146 <https://github.com/mauvilsa/jsonargparse/issues/146>`__).
- AST resolver now supports ``pop`` and ``get`` from ``**kwargs``.

Fixed
^^^^^
- `file:///` scheme not working in windows (`#144
  <https://github.com/mauvilsa/jsonargparse/issues/144>`__).
- Instantiation links with source an entire subclass incorrectly showed
  ``--*.help``.
- Ensure AST-based parameter resolver handles value-less type annotations without error
  (`#148 <https://github.com/mauvilsa/jsonargparse/issues/148>`__).
- Discarding ``init_args`` on ``class_path`` change not working for ``Union``
  with mixed non-subclass types.
- In some cases debug logs not shown even though ``JSONARGPARSE_DEBUG`` set.

Changed
^^^^^^^
- Instantiation links with source an entire class no longer requires to have a
  compute function.
- Instantiation links no longer restricted to first nesting level.
- AST parameter resolver now only logs debug messages instead of failing (`#146
  <https://github.com/mauvilsa/jsonargparse/issues/146>`__).
- Documented AST resolver support for ``**kwargs`` use in property.


v4.11.0 (2022-07-12)
--------------------

Added
^^^^^
- ``env_prefix`` property now also accepts boolean. If set to False, no prefix
  is used for environment variable names (`#145
  <https://github.com/mauvilsa/jsonargparse/pull/145>`__).
- ``link_arguments`` support target being an entire subclass object
  (`lightning#13539
  <https://github.com/Lightning-AI/lightning/discussions/13539>`__).

Fixed
^^^^^
- Method resolution order not working correctly in parameter resolvers (`#143
  <https://github.com/mauvilsa/jsonargparse/issues/143>`__).

Deprecated
^^^^^^^^^^
- ``env_prefix`` property will no longer accept ``None`` in v5.0.0.


v4.10.2 (2022-07-01)
--------------------

Fixed
^^^^^
- AST resolver fails for ``self._kwargs`` assign when a type hint is added.


v4.10.1 (2022-06-29)
--------------------

Fixed
^^^^^
- "Component not supported" crash instead of no parameters (`#141
  <https://github.com/mauvilsa/jsonargparse/issues/141>`__).
- Default from ``default_config_files`` not shown in help when argument has no
  default.
- Only ``init_args`` in later config overwrites instead of updates (`#142
  <https://github.com/mauvilsa/jsonargparse/issues/142>`__).


v4.10.0 (2022-06-21)
--------------------

Added
^^^^^
- Signature parameters resolved by inspecting the source code with ASTs
  (`lightning#11653
  <https://github.com/Lightning-AI/lightning/issues/11653>`__).
- Support init args for unresolved parameters in subclasses (`#114
  <https://github.com/mauvilsa/jsonargparse/issues/114>`__).
- Allow providing a config with ``init_args`` but no ``class_path`` (`#113
  <https://github.com/mauvilsa/jsonargparse/issues/113>`__).

Fixed
^^^^^
- ``dump`` with ``skip_default=True`` not working for subclasses without
  ``init_args`` and when a default value requires serializing.
- ``JSONARGPARSE_DEFAULT_ENV`` should have precedence over given value.
- Giving an invalid class path and then init args would print a misleading error
  message about the init arg instead of the class.
- In some cases ``print_config`` could output invalid values. Now a lenient
  check is done while dumping.
- Resolved some issues related to the logger property and reconplogger.
- Single dash ``'-'`` incorrectly parsed as ``[None]``.

Changed
^^^^^^^
- ``dataclasses`` no longer an optional, now an install require on python 3.6.
- Parameters of type ``POSITIONAL_OR_KEYWORD`` now considered ``KEYWORD`` (`#98
  <https://github.com/mauvilsa/jsonargparse/issues/98>`__).
- Some refactoring mostly related but not limited to the new AST support.
- ``JSONARGPARSE_DEBUG`` now also sets the reconplogger level to ``DEBUG``.
- Renamed the test files to follow the more standard ``test_*.py`` pattern.
- Now ``bool(Namespace())`` evaluates to ``False``.
- When a ``class_path`` is overridden, now only the config values that the new
  subclass doesn't accept are discarded.

Deprecated
^^^^^^^^^^
- ``logger`` property will no longer accept ``None`` in v5.0.0.


v4.9.0 (2022-06-01)
-------------------

Fixed
^^^^^
- ActionsContainer not calling ``LoggerProperty.__init__``.
- For type ``Union[type, List[type]`` when previous value is ``None`` then
  ``--arg+=elem`` should result in a list with single element.

Changed
^^^^^^^
- ``Literal`` options now shown in metavar like choices (`#106
  <https://github.com/mauvilsa/jsonargparse/issues/106>`__).
- ``tuple`` metavar now shown as ``[ITEM,...]``.
- Required arguments with ``None`` default now shown without brackets in usage.
- Improved description of ``--print_config`` in help.


v4.8.0 (2022-05-26)
-------------------

Added
^^^^^
- Support append to lists both from command line and config file (`#85
  <https://github.com/mauvilsa/jsonargparse/issues/85>`__).
- New ``register_unresolvable_import_paths`` function to allow getting the
  import paths of objects that don't have a proper ``__module__`` attribute
  (`lightning#13092
  <https://github.com/Lightning-AI/lightning/issues/13092>`__).
- New unit test for merge of config file ``init_args`` when ``class_path`` does
  not change (`#89 <https://github.com/mauvilsa/jsonargparse/issues/89>`__).

Changed
^^^^^^^
- Replaced custom pre-commit script with a .pre-commit-config.yaml file.
- All warnings are now caught in unit tests.
- Moved ``return_parser`` tests to deprecated tests module.


v4.7.3 (2022-05-10)
-------------------

Fixed
^^^^^
- ``sub_add_kwargs`` not propagated for parameters of final classes.
- New union syntax not working (`#136
  <https://github.com/mauvilsa/jsonargparse/issues/136>`__).


v4.7.2 (2022-04-29)
-------------------

Fixed
^^^^^
- Make ``import_docstring_parse`` backward compatible to support released
  versions of ``LightningCLI`` (`lightning#12918
  <https://github.com/Lightning-AI/lightning/pull/12918>`__).


v4.7.1 (2022-04-26)
-------------------

Fixed
^^^^^
- Properly catch exceptions when parsing docstrings (`lightning#12883
  <https://github.com/Lightning-AI/lightning/issues/12883>`__).


v4.7.0 (2022-04-20)
-------------------

Fixed
^^^^^
- Failing to parse strings that look like timestamps (`#135
  <https://github.com/mauvilsa/jsonargparse/issues/135>`__).
- Correctly consider nested mapping type without args as supported.
- New registered types incorrectly considered as class type.

Changed
^^^^^^^
- Final classes now added as group of actions instead of one typehint action.
- ``@final`` decorator now an import from typing_extensions if available.
- Exporting ``ActionsContainer`` to show respective methods in documentation.
- Raise ValueError when logger property given dict with unexpected key.


v4.6.0 (2022-04-11)
-------------------

Added
^^^^^
- Dump option to exclude entries whose value is the same as the default (`#91
  <https://github.com/mauvilsa/jsonargparse/issues/91>`__).
- Support specifying ``class_path`` only by name for known subclasses (`#84
  <https://github.com/mauvilsa/jsonargparse/issues/84>`__).
- ``add_argument`` with subclass type now also adds ``--*.help`` option.
- Support shorter subclass command line arguments by not requiring to have
  ``.init_args.``.
- Support for ``Literal`` backport from typing_extensions on python 3.7.
- Support nested subclass ``--*.help CLASS`` options.

Changed
^^^^^^^
- ``class_path``'s on parse are now normalized to shortest form.


v4.5.0 (2022-03-29)
-------------------

Added
^^^^^
- ``capture_parser`` function to get the parser object from a cli function.
- ``dump_header`` property to set header for yaml/jsonnet dumpers (`#79
  <https://github.com/mauvilsa/jsonargparse/issues/79>`__).
- ``Callable`` type now supports callable classes (`#110
  <https://github.com/mauvilsa/jsonargparse/issues/110>`__).

Fixed
^^^^^
- Bug in check for ``class_path``, ``init_args`` dicts.
- Module mocks in cli_tests.py.

Changed
^^^^^^^
- Moved argcomplete code from core to optionals module.
- ``Callable`` no longer a simple registered type.
- Import paths are now serialized as its shortest form.
- ``Callable`` default now shown in help as full import path.
- Moved typehint code from core to typehint module.
- Ignore argument links when source/target subclass does not have parameter
  (`#129 <https://github.com/mauvilsa/jsonargparse/issues/129>`__).
- Swapped order of argument links in help to ``source --> target``.

Deprecated
^^^^^^^^^^
- ``CLI``'s ``return_parser`` parameter will be removed in v5.0.0.


v4.4.0 (2022-03-18)
-------------------

Added
^^^^^
- Environment variables to enable features without code change:
    - ``JSONARGPARSE_DEFAULT_ENV`` to enable environment variable parsing.
    - ``JSONARGPARSE_DEBUG`` to print of stack trace on parse failure.

Fixed
^^^^^
- No error message for unrecognized arguments (`lightning#12303
  <https://github.com/Lightning-AI/lightning/issues/12303>`__).

Changed
^^^^^^^
- Use yaml.CSafeLoader for yaml loading if available.


v4.3.1 (2022-03-01)
-------------------

Fixed
^^^^^
- Incorrect use of ``yaml_load`` with jsonnet parser mode (`#125
  <https://github.com/mauvilsa/jsonargparse/issues/125>`__).
- Load of subconfigs not correctly changing working directory (`#125
  <https://github.com/mauvilsa/jsonargparse/issues/125>`__).
- Regression introduced in commit 97e4567 fixed and updated unit test to prevent
  it (`#128 <https://github.com/mauvilsa/jsonargparse/issues/128>`__).
- ``--print_config`` fails for subcommands when ``default_env=True`` (`#126
  <https://github.com/mauvilsa/jsonargparse/issues/126>`__).


v4.3.0 (2022-02-22)
-------------------

Added
^^^^^
- Subcommands now also consider parent parser's ``default_config_files``
  (`lightning#11622
  <https://github.com/Lightning-AI/lightning/pull/11622>`__).
- Automatically added group config load options are now shown in the help #121.

Fixed
^^^^^
- Dumper for ``jsonnet`` should be json instead of yaml (`#123
  <https://github.com/mauvilsa/jsonargparse/issues/123>`__).
- ``jsonnet`` import path not working correctly (`#122
  <https://github.com/mauvilsa/jsonargparse/issues/122>`__).

Changed
^^^^^^^
- ``ArgumentParser`` objects are now pickleable (`lightning#12011
  <https://github.com/Lightning-AI/lightning/pull/12011>`__).


v4.2.0 (2022-02-09)
-------------------

Added
^^^^^
- ``object_path_serializer`` and ``import_object`` support class methods #99.
- ``parser_mode`` is now a property that when set, propagates to subparsers.
- ``add_method_arguments`` also add parameters from same method of parent
  classes when ``*args`` or ``**kwargs`` present.

Fixed
^^^^^
- Optional Enum types incorrectly adding a ``--*.help`` argument.
- Specific errors for invalid value for ``--*.help class_path``.


v4.1.4 (2022-01-26)
-------------------

Fixed
^^^^^
- Subcommand parsers not using the parent's ``parser_mode``.
- Namespace ``__setitem__`` failing when key corresponds to a nested dict.


v4.1.3 (2022-01-24)
-------------------

Fixed
^^^^^
- String within curly braces parsed as dict due to yaml spec implicit values.


v4.1.2 (2022-01-20)
-------------------

Fixed
^^^^^
- Namespace TypeError with non-str inputs (`#116
  <https://github.com/mauvilsa/jsonargparse/issues/116>`__).
- ``print_config`` failing on subclass with required arguments (`#115
  <https://github.com/mauvilsa/jsonargparse/issues/115>`__).


v4.1.1 (2022-01-13)
-------------------

Fixed
^^^^^
- Bad config merging in ``handle_subcommands`` (`lightning#10859
  <https://github.com/Lightning-AI/lightning/issues/10859>`__).
- Unit tests failing with argcomplete>=2.0.0.


v4.1.0 (2021-12-06)
-------------------

Added
^^^^^
- ``set_loader`` function to allow replacing default yaml loader or adding a
  new parser mode.
- ``set_dumper`` function to allow changing default dump formats or adding new
  named dump formats.
- ``parser_mode='omegaconf'`` option to use OmegaConf as a loader, adding
  variable interpolation support.

Fixed
^^^^^
- ``class_from_function`` missing dereference of string return type (`#105
  <https://github.com/mauvilsa/jsonargparse/issues/105>`__).


v4.0.4 (2021-11-29)
-------------------

Fixed
^^^^^
- Linking of attributes applied on instantiation ignoring compute_fn.
- Show full class paths in ``--*.help`` description to avoid misinterpretation.
- ``--*.help`` action failing when fail_untyped and/or skip is required. (`#101
  <https://github.com/mauvilsa/jsonargparse/issues/101>`__).
- Raise exception if lazy_instance called with invalid lazy_kwargs.
- Only add subclass defaults on defaults merging (`#103
  <https://github.com/mauvilsa/jsonargparse/issues/103>`__).
- Strict type and required only on final config check (`#31
  <https://github.com/mauvilsa/jsonargparse/issues/31>`__).
- instantiate_classes failing for type hints with ``nargs='+'``.
- Useful error message when init_args value invalid.
- Specific error message when subclass dict has unexpected keys.
- Removed unnecessary recursive calls causing slow parsing.


v4.0.3 (2021-11-23)
-------------------

Fixed
^^^^^
- Command line parsing of init_args failing with subclasses without a default.
- get_default failing when destination key does not exist in default config file.
- Fixed issue with empty help string caused by a change in argparse python 3.9.


v4.0.2 (2021-11-22)
-------------------

Fixed
^^^^^
- Specifying init_args from the command line resulting in empty namespace when
  no prior class_path given.
- Fixed command line parsing of class_path and init_args options within
  subcommand.
- lazy_instance of final class leading to incorrect default that includes
  class_path and init_args.
- add_subclass_arguments not accepting a default keyword parameter.
- Make it possible to disable deprecation warnings.


v4.0.0 (2021-11-16)
-------------------

Added
^^^^^
- New Namespace class that natively supports nesting and avoids flat/dict
  conversions.
- python 3.10 is now supported and included in circleci tests.
- Readme changed to use doctest and tests are run in github workflow.
- More type hints throughout the code base.
- New unit tests to increase coverage.
- Include dataclasses extras require for tox testing.
- Automatic namespace to dict for link based on target or compute_fn type.

Fixed
^^^^^
- Fixed issues related to conflict namespace base.
- Fixed the parsing of ``Dict[int, str]`` type (`#87
  <https://github.com/mauvilsa/jsonargparse/issues/87>`__).
- Fixed inner relative config with for commented tests for parse_env and CLI.
- init_args from default_config_files not discarded when class_path is
  overridden.
- Problems with class instantiation for parameters of final classes.
- dump/save not removing linked target keys.
- lazy_instance not working with torch.nn.Module (`#96
  <https://github.com/mauvilsa/jsonargparse/issues/96>`__).

Changed
^^^^^^^
- General refactoring and cleanup related to new Namespace class.
- Parsed values from ActionJsonSchema/ActionJsonnet are now dict instead of
  Namespace.
- Removed support for python 3.5 and related code cleanup.
- contextvars package is now an install require for python 3.6.
- Deprecations are now shown as JsonargparseDeprecationWarning.

Deprecated
^^^^^^^^^^
- ArgumentParser's ``parse_as_dict`` option will be removed in v5.0.0.
- ArgumentParser's ``instantiate_subclasses`` method will be removed in v5.0.0.

Removed
^^^^^^^
- python 3.5 is no longer supported.


v3.19.4 (2021-10-04)
--------------------

Fixed
^^^^^
- self.logger undefined on SignatureArguments (`#92
  <https://github.com/mauvilsa/jsonargparse/issues/92>`__).
- Fix linking for deep targets (`#75
  <https://github.com/mauvilsa/jsonargparse/pull/75>`__).
- Fix import_object failing with "not enough values to unpack" (`#94
  <https://github.com/mauvilsa/jsonargparse/issues/94>`__).
- Yaml representer error when dumping unregistered default path type.


v3.19.3 (2021-09-16)
--------------------

Fixed
^^^^^
- add_subclass_arguments with required=False failing on instantiation (`#83
  <https://github.com/mauvilsa/jsonargparse/issues/83>`__).


v3.19.2 (2021-09-09)
--------------------

Fixed
^^^^^
- add_subclass_arguments with required=False failing when not given (`#83
  <https://github.com/mauvilsa/jsonargparse/issues/83>`__).


v3.19.1 (2021-09-03)
--------------------

Fixed
^^^^^
- Repeated instantiation of dataclasses (`lightning#9207
  <https://github.com/Lightning-AI/lightning/issues/9207>`__).


v3.19.0 (2021-08-27)
--------------------

Added
^^^^^
- ``save`` now supports saving to an fsspec path (`#86
  <https://github.com/mauvilsa/jsonargparse/issues/86>`__).

Fixed
^^^^^
- Multifile save not working correctly for subclasses (`#63
  <https://github.com/mauvilsa/jsonargparse/issues/63>`__).
- ``link_arguments`` not working for subcommands (`#82
  <https://github.com/mauvilsa/jsonargparse/issues/82>`__).

Changed
^^^^^^^
- Multiple subcommand settings without explicit subcommand is now a warning
  instead of exception.


v3.18.0 (2021-08-18)
--------------------

Added
^^^^^
- Support for parsing ``Mapping`` and ``MutableMapping`` types.
- Support for parsing ``frozenset``, ``MutableSequence`` and ``MutableSet`` types.

Fixed
^^^^^
- Don't discard ``init_args`` with non-changing ``--*.class_path`` argument.
- Don't ignore ``KeyError`` in call to instantiate_classes (`#81
  <https://github.com/mauvilsa/jsonargparse/issues/81>`__).
- Optional subcommands fail with a KeyError (`#68
  <https://github.com/mauvilsa/jsonargparse/issues/68>`__).
- Conflicting namespace for subclass key in subcommand.
- ``instantiate_classes`` not working for subcommand keys (`#70
  <https://github.com/mauvilsa/jsonargparse/issues/70>`__).
- Proper file not found message from _ActionConfigLoad (`#64
  <https://github.com/mauvilsa/jsonargparse/issues/64>`__).
- ``parse_path`` not parsing inner config files.

Changed
^^^^^^^
- Docstrings no longer supported for python 3.5.
- Show warning when ``--*.class_path`` discards previous ``init_args``.
- Trigger error when ``parse_args`` called with non-string value.
- ActionParser accepts both title and help, title having preference.
- Multiple subcommand settings allowed if explicit subcommand given.


v3.17.0 (2021-07-19)
--------------------

Added
^^^^^
- ``datetime.timedelta`` now supported as a type.
- New function ``class_from_function`` to add signature of functions that
  return an instantiated class.

Fixed
^^^^^
- ``--*.init_args.*`` causing crash when overriding value from config file.


v3.16.1 (2021-07-13)
--------------------

Fixed
^^^^^
- Signature functions not working for classes implemented with ``__new__``.
- ``instantiate_classes`` failing when keys not present in config object.


v3.16.0 (2021-07-05)
--------------------

Added
^^^^^
- ``lazy_instance`` function for serializable class type defaults.
- Support for parsing multiple matched default config files (`#58
  <https://github.com/mauvilsa/jsonargparse/issues/58>`__).

Fixed
^^^^^
- ``--*.class_path`` and ``--*.init_args.*`` arguments not being parsed.
- ``--help`` broken when default_config_files fail to parse (`#60
  <https://github.com/mauvilsa/jsonargparse/issues/60>`__).
- Pattern in default_config_files not using sort.


v3.15.0 (2021-06-22)
--------------------

Added
^^^^^
- Decorator for final classes and an is_final_class function to test it.
- Support for final classes as type hint.
- ``add_subclass_arguments`` now supports multiple classes given as tuple.
- ``add_subclass_arguments`` now supports the instantiate parameter.

Fixed
^^^^^
- Parsing of relative paths inside inner configs for type hint actions.


v3.14.0 (2021-06-08)
--------------------

Added
^^^^^
- Method ``instantiate_classes`` that instantiates subclasses and class groups.
- Support for ``link_arguments`` that are applied on instantiation.
- Method ``add_subclass_arguments`` now supports skipping of arguments.
- Added support for Type in type hints (`#59
  <https://github.com/mauvilsa/jsonargparse/issues/59>`__).

Fixed
^^^^^
- Custom string template to avoid problems with percent symbols in docstrings.


v3.13.1 (2021-06-03)
--------------------

Fixed
^^^^^
- Type hint Any not correctly serializing Enum and registered type values.


v3.13.0 (2021-06-02)
--------------------

Added
^^^^^
- Inner config file support for subclass type hints in signatures and CLI (`#57
  <https://github.com/mauvilsa/jsonargparse/issues/57>`__).
- Forward fail_untyped setting to nested subclass type hints.

Fixed
^^^^^
- With fail_untyped=True use type from default value instead of Any.
- Registered types and typing types incorrectly considered subclass types.

Changed
^^^^^^^
- Better structure of type hint error messages to ease understanding.


v3.12.1 (2021-05-19)
--------------------

Fixed
^^^^^
- ``--print_config`` can now be given before other arguments without value.
- Fixed conversion of flat namespace to dict when there is a nested empty namespace.
- Fixed issue with get_defaults with default config file and parse_as_dict=False.
- Fixed bug in save which failed when there was an int key.

Changed
^^^^^^^
- ``--print_config`` now only receives a value with ``=`` syntax.
- ``add_{class,method,function,dataclass}_arguments`` now return a list of
  added arguments.


v3.12.0 (2021-05-13)
--------------------

Added
^^^^^
- Path support for fsspec file systems using the 's' mode flag.
- set_config_read_mode function that can enable fsspec for config reading.
- Option for print_config and dump with help as yaml comments.

Changed
^^^^^^^
- print_config only added to parsers when ActionConfigFile is added.

Deprecated
^^^^^^^^^^
- set_url_support functionality now should be done with set_config_read_mode.


v3.11.2 (2021-05-03)
--------------------

Fixed
^^^^^
- Link argument arrow ``<=`` can be confused as less or equal, changed to
  ``<--``.


v3.11.1 (2021-04-30)
--------------------

Fixed
^^^^^
- add_dataclass_arguments not making parameters without default as required (`#54
  <https://github.com/mauvilsa/jsonargparse/issues/54>`__).
- Removed from signature add methods required option included by mistake.


v3.11.0 (2021-04-27)
--------------------

Added
^^^^^
- CLI now has ``--config`` options at subcommand and subsubcommand levels.
- CLI now adds subcommands with help string taken from docstrings.
- print_config at subcommand level for global config with implicit subcommands.
- New Path_drw predefined type.
- Type hint arguments now support ``nargs='?'``.
- Signature methods can now skip arguments within init_args of subclasses.

Changed
^^^^^^^
- Removed skip_check from ActionPathList which was never implemented.

Deprecated
^^^^^^^^^^
- ActionPath should no longer be used, instead paths are given as type.

Fixed
^^^^^
- Actions not being applied for subsubcommand values.
- handle_subcommands not correctly inferring subsubcommand.


v3.10.1 (2021-04-24)
--------------------

Changed
^^^^^^^
- fail_untyped now adds untyped parameters as type Any and if no default
  then default set to None.

Fixed
^^^^^
- ``--*.help`` option being added for non-subclass types.
- Iterable and Sequence types not working for python>=3.7 (`#53
  <https://github.com/mauvilsa/jsonargparse/issues/53>`__).


v3.10.0 (2021-04-19)
--------------------

Added
^^^^^
- set_defaults method now works for arguments within subcommands.
- CLI set_defaults option to allow overriding of defaults.
- CLI return_parser option to ease inclusion in documentation.
- save_path_content attribute to save paths content on config save.
- New ``link_arguments`` method to derive an argument value from others.
- print_config now includes subclass init_args if class_path given.
- Subclass type hints now also have a ``--*.help`` option.

Changed
^^^^^^^
- Signature parameters whose name starts with "_" are skipped.
- The repr of Path now has the form ``Path_{mode}(``.

Fixed
^^^^^
- CLI now does instantiate_subclasses before running.


v3.9.0 (2021-04-09)
-------------------

Added
^^^^^
- New method add_dataclass_arguments.
- Dataclasses are now supported as a type.
- New predefined type Path_dc.
- Experimental Callable type support.
- Signature methods with nested key can be made required.
- Support for Literal types.
- New option in signatures methods to not fail for untyped required.

Changed
^^^^^^^
- Generation of yaml now uses internally pyyaml's safe_dump.
- New cleaner implementation for type hints support.
- Moved deprecated code to a module specific for this.
- Path types repr now has format Path(rel[, cwd=dir]).
- instantiate_subclasses now always returns a dict.

Deprecated
^^^^^^^^^^
- ActionEnum should no longer be used, instead enums are given as type.

Fixed
^^^^^
- Deserialization of types not being done for nested config files.


v3.8.1 (2021-03-22)
-------------------

Fixed
^^^^^
- Help fails saying required args missing if default config file exists (`#48
  <https://github.com/mauvilsa/jsonargparse/issues/48>`__).
- ActionYesNo arguments failing when parsing from environment variable (`#49
  <https://github.com/mauvilsa/jsonargparse/issues/49>`__).


v3.8.0 (2021-03-22)
-------------------

Added
^^^^^
- Path class now supports home prefix '~' (`#45
  <https://github.com/mauvilsa/jsonargparse/issues/45>`__).
- yaml/json dump kwargs can now be changed via attributes dump_yaml_kwargs and
  dump_json_kwargs.

Changed
^^^^^^^
- Now by default dump/save/print_config preserve the add arguments and argument
  groups order (only CPython>=3.6) (`#46
  <https://github.com/mauvilsa/jsonargparse/issues/46>`__).
- ActionParser group title now defaults to None if not given (`#47
  <https://github.com/mauvilsa/jsonargparse/issues/47>`__).
- Add argument with type Enum or type hint giving an action now raises error
  (`#45 <https://github.com/mauvilsa/jsonargparse/issues/45>`__).
- Parser help now also considers default_config_files and shows which config file
  was loaded (`#47 <https://github.com/mauvilsa/jsonargparse/issues/47>`__).
- get_default method now also considers default_config_files.
- get_defaults now raises ParserError if default config file not valid.

Fixed
^^^^^
- default_config_files property not removing help group when setting None.


v3.7.0 (2021-03-17)
-------------------

Changed
^^^^^^^
- ActionParser now moves all actions to the parent parser.
- The help of ActionParser arguments is now shown in the main help (`#41
  <https://github.com/mauvilsa/jsonargparse/issues/41>`__).

Fixed
^^^^^
- Use of required in ActionParser parsers not working (`#43
  <https://github.com/mauvilsa/jsonargparse/issues/43>`__).
- Nested options with names including dashes not working (`#42
  <https://github.com/mauvilsa/jsonargparse/issues/42>`__).
- DefaultHelpFormatter not properly using env_prefix to show var names.


v3.6.0 (2021-03-08)
-------------------

Added
^^^^^
- Function to register additional types for use in parsers.
- Type hint support for complex and UUID classes.

Changed
^^^^^^^
- PositiveInt and NonNegativeInt now gives error instead of silently truncating
  when given float.
- Types created with restricted_number_type and restricted_string_type now share
  a common TypeCore base class.

Fixed
^^^^^
- ActionOperators not give error if type already registered.
- List[Tuple] types not working correctly.
- Some nested dicts kept as Namespace by dump.


v3.5.1 (2021-02-26)
-------------------

Fixed
^^^^^
- Parsing of relative paths in default_config_files not working.
- Description of tuple type in the readme.


v3.5.0 (2021-02-12)
-------------------

Added
^^^^^
- Tuples with ellipsis are now supported (`#40
  <https://github.com/mauvilsa/jsonargparse/issues/40>`__).

Fixed
^^^^^
- Using dict as type incorrectly considered as class requiring class_path.
- Nested tuples were not working correctly (`#40
  <https://github.com/mauvilsa/jsonargparse/issues/40>`__).


v3.4.1 (2021-02-03)
-------------------

Fixed
^^^^^
- CLI crashed for class method when zero args given after subcommand.
- Options before subcommand provided in config file gave subcommand not given.
- Arguments in groups without help not showing required, type and default.
- Required arguments help incorrectly showed null default value.
- Various improvements and fixes to the readme.


v3.4.0 (2021-02-01)
-------------------

Added
^^^^^
- Save with multifile=True now creates original jsonnet file for ActionJsonnet.
- default_config_files is now a property of parser objects.
- Table in readme to ease understanding of extras requires for optional features
  (`#38 <https://github.com/mauvilsa/jsonargparse/issues/38>`__).

Changed
^^^^^^^
- Save with multifile=True uses file extension to choose json or yaml format.

Fixed
^^^^^
- Better exception message when using ActionJsonSchema and jsonschema not
  installed (`#38 <https://github.com/mauvilsa/jsonargparse/issues/38>`__).


v3.3.2 (2021-01-22)
-------------------

Fixed
^^^^^
- Changed actions so that keyword arguments are visible in API.
- Fixed save method short description which was copy paste of dump.
- Added missing docstring in instantiate_subclasses method.
- Fixed crash when using ``--help`` and ActionConfigFile not given help string.
- Standardized capitalization and punctuation of: help, config, version.


v3.3.1 (2021-01-08)
-------------------

Fixed
^^^^^
- instantiate_subclasses work properly when init_args not present.
- Addressed a couple of issues pointed out by sonarcloud.


v3.3.0 (2021-01-08)
-------------------

Added
^^^^^
- New add_subclass_arguments method to add as type with a specific help option.


v3.2.1 (2020-12-30)
-------------------

Added
^^^^^
- Automatic Optional for arguments with default None (`#30
  <https://github.com/mauvilsa/jsonargparse/issues/30>`__).
- CLI now supports running methods from classes.
- Signature arguments can now be loaded from independent config files (`#32
  <https://github.com/mauvilsa/jsonargparse/issues/32>`__).
- add_argument now supports enable_path for type based on jsonschema.
- print_config can now be given as value skip_null to exclude null entries.

Changed
^^^^^^^
- Improved description of parser used as standalone and for ActionParser (`#34
  <https://github.com/mauvilsa/jsonargparse/issues/34>`__).
- Removed ``__cwd__`` and top level ``__path__`` that were not needed.

Fixed
^^^^^
- ActionYesNo argument in help the type is now bool.
- Correctly skip self in add_method_arguments for inherited methods.
- Prevent failure of dump in cleanup_actions due to new _ActionConfigLoad.
- Prevent failure in save_paths for dict with int keys.
- Avoid duplicate config check failure message with subcommands.


v3.1.0 (2020-12-09)
-------------------

Added
^^^^^
- Support for multiple levels of subcommands (`#29
  <https://github.com/mauvilsa/jsonargparse/issues/29>`__).
- Default description of subcommands explaining use of ``--help``.


v3.0.1 (2020-12-02)
-------------------

Fixed
^^^^^
- add_class_arguments incorrectly added arguments from ``__call__`` instead
  of ``__init__`` for callable classes.


v3.0.0 (2020-12-01)
-------------------

Added
^^^^^
- Functions to add arguments from classes, methods and functions.
- CLI function that allows creating a line command line interface with a single
  line of code inspired by Fire.
- Typing module that includes predefined types and type generator functions
  for paths and restricted numbers/strings.
- Extended support to add_argument type to allow complex type hints.
- Parsers now include ``--print_config`` option to dump defaults.
- Support argcomplete for tab completion of arguments.

Changed
^^^^^^^
- ArgumentParsers by default now use as error_handler the
  usage_and_exit_error_handler.
- error_handler and formatter_class no longer accept as value a string.
- Changed SimpleNamespace to Namespace to avoid unnecessary differences with
  argparse.

Deprecated
^^^^^^^^^^
- ActionOperators should no longer be used, the new alternative is
  restricted number types.


v2.X.X
------

The change log was introduced in v3.0.0. For details of the changes for previous
versions take a look at the git log. It more or less reads like a change log.
