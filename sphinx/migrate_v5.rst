:orphan:

.. _migrate-v5:

Migrating to v5
===============

This guide helps you migrate from jsonargparse v4 to v5. The recommended
approach is:

1. **Upgrade to the latest v4 release** (``pip install "jsonargparse>=4,<5"``).
2. **Run your code with deprecation warnings enabled** to discover all usages
   that need updating::

       JSONARGPARSE_DEPRECATION_WARNINGS=all python your_script.py

3. **Fix all deprecation warnings** as described in the sections below.
4. **Review the** `Breaking changes summary`_, since some changes do not emit a
   deprecation warning.
5. **Upgrade to v5** (``pip install "jsonargparse>=5"``).

.. note::

   By default, only one warning per type is shown, and some deprecations only
   warn when the variable is set to ``all``. Always use ``all`` to see
   everything that needs updating.


Breaking changes summary
------------------------

In addition to the deprecation removals below, note these other breaking
changes:

- **``pyyaml`` is no longer a required dependency.** Gives no deprecation
  warning. Without it the default ``parser_mode`` and dump format is ``json``.
  If your code imports ``yaml``, or you want yaml configs, install with the
  ``yaml`` extra (``pip install "jsonargparse[yaml]"``).
- **``json`` dumps are now indented.** Gives no deprecation warning.
  ``dump(format="json")``, ``save`` and the print config argument produce
  indented JSON instead of a single line. Use ``format="json_compact"`` for the
  previous output.
- **``--print_config`` renamed.** The print-config argument in v5 defaults to
  ``--print_<config_arg_name>`` instead of always being ``--print_config``, so
  it only stays ``--print_config`` when the config argument is named ``config``.
  Set ``print_config="--print_config"`` in the ``ArgumentParser`` constructor to
  keep the old name. Warns only with ``JSONARGPARSE_DEPRECATION_WARNINGS=all``.
- **Config objects always include metadata.** The ``default_meta=False``
  behavior has been removed; metadata is always present. Use
  ``.clone(with_meta=False)`` to strip it.
- **Subcommand selection is always explicit.** When multiple subcommand settings
  are available in a config, the subcommand must be given explicitly.
- **Untyped/optional signature parameters become required.** For the signature
  methods (``add_class_arguments``, etc.), a parameter with an ``Optional`` type
  but no default, and — when ``fail_untyped=False`` — a required parameter with
  no type annotation, are no longer silently made optional with default
  ``None``; they remain required. Give such parameters an explicit default if
  optional is intended. Warns only with
  ``JSONARGPARSE_DEPRECATION_WARNINGS=all``.
- **Configs can no longer import and instantiate anything.** See `Subclass specs
  and import paths`_ below.


CLI / auto_cli
--------------

``jsonargparse.CLI`` was renamed to :func:`.auto_cli`. The old name is kept as
an alias, so it keeps working, but prefer the new name:

.. code-block:: python

   # before
   from jsonargparse import CLI
   CLI(MyComponent)

   # after
   from jsonargparse import auto_cli
   auto_cli(MyComponent)

The ``return_parser=True`` parameter was removed. Use :func:`.capture_parser`
instead:

.. code-block:: python

   # before
   parser = CLI(MyComponent, return_parser=True)

   # after
   from jsonargparse import auto_cli, capture_parser
   parser = capture_parser(lambda: auto_cli(MyComponent))

Implicit component discovery (calling ``auto_cli`` without a ``components``
argument and relying on the local scope) is removed. Pass components explicitly:

.. code-block:: python

   # before
   auto_cli()  # discovered the components from the caller's context

   # after
   auto_cli([ComponentA, ComponentB])


Parser methods
--------------

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Before
     - After
   * - ``parser.check_config(cfg)``
     - ``parser.validate(cfg)``
   * - ``parser.dump(..., skip_check=True)``
     - ``parser.dump(..., skip_validation=True)``
   * - ``parser.save(..., skip_check=True)``
     - ``parser.save(..., skip_validation=True)``
   * - ``parser.get_defaults(skip_check=True)``
     - ``parser.get_defaults(skip_validation=True)``
   * - ``parser.add_dataclass_arguments(...)``
     - ``parser.add_class_arguments(...)``
   * - ``parser.instantiate_classes(cfg)``
     - ``parser.instantiate(cfg)``
   * - ``parser.instantiate_subclasses(cfg)``
     - ``parser.instantiate(cfg)``
   * - ``parser.add_instantiator(fn, cls)``
     - ``jsonargparse.add_instantiator(fn, cls)``
   * - ``parser.merge_config(a, b)``
     - No replacement (was internal API).


Renamed parameters
------------------

Several public methods renamed parameters for consistency. These only affect
calls that pass the parameter **by keyword**; positional usage is unaffected.

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Before
     - After
   * - ``parse_object(cfg_obj=..., cfg_base=...)``
     - ``parse_object(obj=..., namespace=...)``
   * - ``parse_path(cfg_path=...)``
     - ``parse_path(path=...)``
   * - ``parse_string(cfg_str=..., cfg_path=...)``
     - ``parse_string(content=..., path=...)``
   * - ``cfg=...`` in ``dump``, ``save``, ``validate``, ``instantiate``,
       ``strip_unknown`` and ``get_config_files``
     - ``namespace=...``
   * - ``add_class_arguments(theclass=...)``
     - ``add_class_arguments(class_type=...)``
   * - ``add_method_arguments(theclass=..., themethod=...)``
     - ``add_method_arguments(class_type=..., method_name=...)``
   * - ``register_type(type_class=...)``
     - ``register_type(class_type=...)``


Config objects (Namespace)
--------------------------

**parse_as_dict** — The ``parse_as_dict`` constructor parameter is removed. Call
``.as_dict()`` on the returned ``Namespace`` object instead:

.. code-block:: python

   # before
   parser = ArgumentParser(parse_as_dict=True)
   cfg = parser.parse_args()  # returns dict

   # after
   cfg = parser.parse_args().as_dict()

**with_meta / default_meta** — The ``with_meta`` parameter of ``parse_*``
methods and the ``default_meta`` property are removed. Config objects always
contain metadata. Use ``.clone()`` to control metadata:

.. code-block:: python

   # before
   parser = ArgumentParser(default_meta=False)
   cfg = parser.parse_args(with_meta=False)

   # after
   cfg = parser.parse_args().clone(with_meta=False)

**Utility functions:**

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Before
     - After
   * - ``strip_meta(cfg)``
     - ``cfg.clone(with_meta=False)``
   * - ``namespace_to_dict(cfg)``
     - ``cfg.as_dict()`` or ``cfg.clone().as_dict()``
   * - ``dict_to_namespace(d)``
     - Removed — use ``parser.parse_object(d)`` for safe conversion
   * - ``ns.get_sorted_keys()``
     - ``sorted(ns.keys())``
   * - ``ns.get_value_and_parent(key)``
     - Access parent and leaf key separately via ``ns``


dump / save / validate
-----------------------

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Before
     - After
   * - ``parser.dump(cfg, yaml_comments=True)``
     - ``parser.dump(cfg, with_comments=True)``
   * - ``parser.dump(cfg, skip_none=True)``
     - ``parser.dump(cfg, skip_unset=True)``
   * - ``parser.save(cfg, skip_none=True)``
     - ``parser.save(cfg, skip_unset=True)``
   * - ``parser.validate(cfg, skip_none=True)``
     - ``parser.validate(cfg, skip_unset=True)``
   * - ``--print_config skip_null``
     - ``--print_config skip_unset``


Paths
-----

**Legacy action classes** — Replace ``ActionPath`` and ``ActionPathList`` with
type hints:

.. code-block:: python

   from jsonargparse.typing import path_type

   # before
   parser.add_argument("--file", action=ActionPath(mode="fr"))
   parser.add_argument("--files", action=ActionPathList(mode="fr"))

   # after
   parser.add_argument("--file", type=path_type("fr"))
   parser.add_argument("--files", type=list[path_type("fr")], sub_configs=True)

**Path object API changes:**

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Before
     - After
   * - ``path()`` or ``path(absolute=False)``
     - ``path.absolute`` or ``path.relative``
   * - ``path.abs_path``
     - ``path.absolute``
   * - ``path.rel_path``
     - ``path.relative``
   * - ``path.get_content()``
     - ``path.read_text()`` (text) or ``path.open()`` (binary)
   * - ``Path(..., skip_check=True)``
     - Use ``str`` or ``os.PathLike`` instead
   * - ``path.rel_path = ...``, ``path.abs_path = ...``, ``path.cwd = ...``
     - Path objects are immutable, create a new ``Path`` instead

**enable_path parameter:**

.. code-block:: python

   # before
   parser.add_argument("--cfg", type=MyType, enable_path=True)
   ActionJsonSchema(schema=s, enable_path=True)

   # after
   parser.add_argument("--cfg", type=MyType, sub_configs=True)
   ActionJsonSchema(schema=s, sub_config=True)


Legacy action classes
---------------------

``ActionEnum`` and ``ActionOperators`` are removed. Pass types directly:

.. code-block:: python

   from jsonargparse.typing import restricted_number_type

   # before
   parser.add_argument("--color", action=ActionEnum(enum=Color))
   parser.add_argument("--lr", action=ActionOperators(expr=(">=", 0.0), type=float))

   # after
   parser.add_argument("--color", type=Color)
   PositiveFloat = restricted_number_type("PositiveFloat", float, (">=", 0.0))
   parser.add_argument("--lr", type=PositiveFloat)

``ActionJsonnetExtVars`` is removed. Use ``type=dict`` instead:

.. code-block:: python

   # before
   parser.add_argument("--ext_vars", action=ActionJsonnetExtVars())

   # after
   parser.add_argument("--ext_vars", type=dict)


Settings functions
------------------

The standalone settings functions are replaced by :func:`.set_parsing_settings`:

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Before
     - After
   * - ``set_url_support(True)``
     - ``set_parsing_settings(config_read_mode_urls_enabled=True)``
   * - ``set_config_read_mode(urls_enabled=True)``
     - ``set_parsing_settings(config_read_mode_urls_enabled=True)``
   * - ``set_config_read_mode(fsspec_enabled=True)``
     - ``set_parsing_settings(config_read_mode_fsspec_enabled=True)``
   * - ``set_docstring_parse_options(style=s, attribute_docstrings=True)``
     - ``set_parsing_settings(docstring_parse_style=s, docstring_parse_attribute_docstrings=True)``
   * - ``get_config_read_mode()``
     - Removed (internal).


Subclass specs and import paths
-------------------------------

Two defaults change so that a config from an untrusted source can't reach
arbitrary code. Both give a deprecation warning in v4.

**Subclass specs in types that accept any value** — A dict with ``class_path``
and ``init_args`` given for a type that accepts any value, i.e. ``Any``,
``object``, ``Unvalidated<...>`` or an untyped parameter when
``fail_untyped=False``, is currently imported and instantiated by
``instantiate``. In v5 it is kept as is, so that the code that receives it
decides whether to instantiate it. Get the v5 behavior in v4 with:

.. code-block:: python

   from jsonargparse import set_parsing_settings

   set_parsing_settings(instantiate_subclass_spec_in_any=False)

If the value must be an instance, annotate the parameter with the expected class
instead of a type that accepts any value. Setting it to ``True`` keeps the v4
behavior and silences the warning, but is discouraged since it means that a
config is able to instantiate any class. See :ref:`sub-classes`.

**Denied import paths** — Import paths given as a value, e.g. a ``class_path``
of ``subprocess.Popen``, are checked against a denylist of standard library
paths that give code execution. In v4 a denied path only warns and the import
proceeds. In v5 it fails. Giving a value to either setting, an empty list
included, enforces the denylist in v4:

.. code-block:: python

   set_parsing_settings(import_path_denylist=[])

If a path that the application legitimately uses is denied, add it to
``import_path_allowlist``. For configs that are entirely untrusted, deny
everything and allow only what is expected, see :ref:`untrusted-configs`:

.. code-block:: python

   set_parsing_settings(
       import_path_denylist=["*"],
       import_path_allowlist=["mypackage.tools"],
   )


Logging and error handling
--------------------------

``LoggerProperty`` is removed. jsonargparse no longer ships a logging helper;
use your own logging setup.

The ``error_handler`` property and ``usage_and_exit_error_handler`` are removed.
Use the standard argparse ``exit_on_error`` parameter instead: ``True``, the
default, prints the usage and exits, and ``False`` raises an ``ArgumentError``:

.. code-block:: python

   parser = ArgumentParser(exit_on_error=False)

``usage_and_exit_error_handler`` did what argparse does by default, so it is
removed without a replacement. For a custom handler, use ``exit_on_error=False``
and handle the raised ``ArgumentError``.

``logger=None`` and ``env_prefix=None`` in v5 raise an error. Use ``False`` or
``True`` respectively:

.. code-block:: python

   parser.logger = False     # was: parser.logger = None
   parser.env_prefix = True  # was: parser.env_prefix = None


Miscellaneous
-------------

- **``compose_dataclasses``** is removed. There is no replacement; copy the
  helper into your own code if needed.
- **``DefaultHelpFormatter.*_yaml*_comment*`` methods** are removed (this logic
  is now internal).
- **``ruyaml`` optional dependency** is replaced by ``ruamel``. Update your
  extras install: ``pip install "jsonargparse[ruyaml]"`` → ``pip install
  "jsonargparse[ruamel]"``.
- **``ParserError``** is removed. It was an alias of ``argparse.ArgumentError``,
  use that instead.
- **``null_logger``** is removed. There is no replacement since it is a logging
  detail, use ``logging.getLogger`` with a ``NullHandler``.
- **Importing from internal module paths** (e.g. ``jsonargparse.core``,
  ``jsonargparse.actions``, ``jsonargparse.typehints``) no longer works. Import
  only from the public API (``jsonargparse`` and ``jsonargparse.typing``).
