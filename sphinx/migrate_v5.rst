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
4. **Upgrade to v5** (``pip install "jsonargparse>=5"``).

.. note::

   By default, only one warning per type is shown. Setting the environment
   variable to ``all`` ensures every occurrence is reported.


Breaking changes summary
------------------------

In addition to the deprecation removals below, note these other breaking
changes:

- **Python ≥ 3.10 required.** Support for Python 3.9 (and earlier) has been
  dropped.
- **``pyyaml`` is no longer a required dependency.** If your code relies on it,
  install with the ``yaml`` extra (``pip install "jsonargparse[yaml]"``).
- **``--print_config`` renamed.** The print-config argument now defaults to
  ``--print_<config_arg_name>`` instead of always being ``--print_config``.
  Update any scripts or docs that reference ``--print_config`` explicitly.
- **Config objects always include metadata.** The ``default_meta=False``
  behaviour has been removed; metadata is always present. Use
  ``.clone(with_meta=False)`` to strip it.
- **Subcommand selection is always explicit.** When multiple subcommand settings
  are available in a config, the subcommand must be specified explicitly.


CLI / auto_cli
--------------

``jsonargparse.CLI`` was renamed to :func:`.auto_cli`.

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
   auto_cli()  # discovered components from caller's module

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
   parser.add_argument("--f", action=ActionPath(mode="fr"))
   parser.add_argument("--files", action=ActionPathList(mode="fr"))

   # after
   parser.add_argument("--f", type=path_type("fr"))
   parser.add_argument("--files", type=List[path_type("fr")], sub_configs=True)

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

   from enum import Enum
   from jsonargparse.typing import restricted_number_type

   # before
   parser.add_argument("--color", action=ActionEnum(enum=Color))
   parser.add_argument("--lr", action=ActionOperators(expr=(">=", 0.0), type=float))

   # after
   parser.add_argument("--color", type=Color)
   PositiveFloat = restricted_number_type("PositiveFloat", float, (">=", 0.0))
   parser.add_argument("--lr", type=PositiveFloat)


Settings functions
------------------

The standalone settings functions are replaced by :func:`.set_parsing_settings`:

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Before
     - After
   * - ``set_url_support(True)``
     - ``set_parsing_settings(config_read_mode="url")``
   * - ``set_config_read_mode(urls_enabled=True)``
     - ``set_parsing_settings(config_read_mode="url")``
   * - ``set_config_read_mode(fsspec_enabled=True)``
     - ``set_parsing_settings(config_read_mode="fsspec")``
   * - ``set_docstring_parse_options(style=s, attribute_docstrings=True)``
     - ``set_parsing_settings(docstring_parse_style=s, docstring_parse_attribute_docstrings=True)``
   * - ``get_config_read_mode()``
     - Removed (internal).


Logging and error handling
--------------------------

``LoggerProperty`` is removed. jsonargparse no longer ships a logging helper;
use your own logging setup.

The ``error_handler`` property is removed. Use the standard argparse
``exit_on_error`` parameter instead:

.. code-block:: python

   # before
   parser.error_handler = usage_and_exit_error_handler

   # after
   parser = ArgumentParser(exit_on_error=True)

``logger=None`` and ``env_prefix=None`` now raise an error. Use ``False`` or
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
- **``dev`` extra** now installs all optional dependencies.
