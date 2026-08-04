.. _auto-cli:

Basic usage
===========

There are multiple ways of using jsonargparse. One is to construct low level
parsers (see :ref:`parsers`) being almost a drop in replacement of argparse.
However, argparse is too verbose and leads to unnecessary duplication. The
simplest and recommended way of using jsonargparse is by using the
:func:`.auto_cli` function, which has the benefit of minimizing boilerplate
code. A simple example is:

.. testcode::

    from jsonargparse import auto_cli


    def command(name: str, prize: int = 100):
        """Prints the prize won by a person.

        Args:
            name: Name of winner.
            prize: Amount won.
        """
        print(f"{name} won {prize}€!")


    if __name__ == "__main__":
        auto_cli(command)

Note that the ``name`` and ``prize`` parameters have type hints and are
described in the docstring. These are shown in the help of the command line
tool. In a shell you could see the help and run a command as follows:

.. code-block:: bash

    $ python example.py --help
    ...
    Prints the prize won by a person:
      name                  Name of winner. (required, type: str)
      --prize PRIZE         Amount won. (type: int, default: 100)

    $ python example.py Lucky --prize=1000
    Lucky won 1000€!

.. note::

    Parsing of docstrings is an optional feature. For this example to work as
    shown, jsonargparse needs to be installed with the ``signatures`` extra
    as explained in section :ref:`installation`.

When :func:`.auto_cli` receives a single class, the first arguments are for
parameters to instantiate the class, then a method name is expected (i.e.
methods become :ref:`sub-commands`) and the remaining arguments are for
parameters of this method. An example would be:

.. testcode::

    from random import randint
    from jsonargparse import auto_cli


    class Main:
        def __init__(self, max_prize: int = 100):
            """
            Args:
                max_prize: Maximum prize that can be awarded.
            """
            self.max_prize = max_prize

        def person(self, name: str):
            """
            Args:
                name: Name of winner.
            """
            return f"{name} won {randint(0, self.max_prize)}€!"


    if __name__ == "__main__":
        print(auto_cli(Main))

Then in a shell you could run:

.. code-block:: bash

    $ python example.py --max_prize=1000 person Lucky
    Lucky won 632€!

.. doctest:: :hide:

    >>> auto_cli(Main, args=["--max_prize=1000", "person", "Lucky"])  # doctest: +ELLIPSIS
    'Lucky won ...€!'

If the given class does not have any methods, there will be no subcommands and
:func:`.auto_cli` will return an instance of the class. For example:

.. testcode::

    from dataclasses import dataclass
    from jsonargparse import auto_cli


    @dataclass
    class Settings:
        name: str
        prize: int = 100


    if __name__ == "__main__":
        print(auto_cli(Settings, as_positional=False))

Then in a shell you could run:

.. code-block:: bash

    $ python example.py --name=Lucky
    Settings(name='Lucky', prize=100)

.. doctest:: :hide:

    >>> auto_cli(Settings, as_positional=False, args=["--name=Lucky"])  # doctest: +ELLIPSIS
    Settings(name='Lucky', prize=100)

Note the use of ``as_positional=False`` to make required arguments
non-positional.

To force class instantiation even when the class has public methods, use
``return_instance=True``. This makes :func:`.auto_cli` parse only the class init
arguments and return the class instance, without adding method subcommands.

If more than one function is given to :func:`.auto_cli`, then any of them can be
run via :ref:`sub-commands` similar to the single class example above, i.e.
``example.py function [arguments]`` where ``function`` is the name of the
function to execute. If multiple classes or a mixture of functions and classes
is given to :func:`.auto_cli`, to execute a method of a class, two levels of
:ref:`sub-commands` are required. The first subcommand would be the name of the
class and the second the name of the method, i.e. ``example.py class
[init_arguments] method [arguments]``.

Arbitrary levels of subcommands with custom names can be defined by providing a
``dict``. For example:

.. testcode::

    class Raffle:
        def __init__(self, prize: int):
            self.prize = prize

        def __call__(self, name: str):
            return f"{name} won {self.prize}€!"

    components = {
        "weekday": {
            "_help": "Raffles for weekdays",
            "tier1": Raffle(prize=100),
            "tier2": Raffle(prize=50),
        },
        "weekend": {
            "_help": "Raffles for weekends",
            "tier1": Raffle(prize=300),
            "tier2": Raffle(prize=75),
        },
    }

    if __name__ == "__main__":
        print(auto_cli(components))

Then in a shell:

.. code-block:: bash

    $ python example.py weekend tier1 Lucky
    Lucky won 300€!

.. doctest:: :hide:

    >>> auto_cli(components, args=["weekend", "tier1", "Lucky"])
    'Lucky won 300€!'

.. note::

    The examples above are extremely simple, only defining parameters with
    ``str`` and ``int`` type hints. The true power of jsonargparse is its
    support for a wide range of types, see :ref:`type-hints`. It is even
    possible to use general classes as type hints, allowing to easily implement
    configurable `dependency injection (object composition)
    <https://en.wikipedia.org/wiki/Dependency_injection>`__, see
    :ref:`sub-classes`.

Writing configuration files
---------------------------

All tools implemented with the :func:`.auto_cli` function have the ``--config``
option to provide settings in a config file (more details in
:ref:`configuration-files`). This is particularly useful when there are many
configurable parameters. To ease the writing of config files, there is also the
option ``--print_config`` which prints to standard output all settings that the
tool supports with their default values. Users can follow these steps:

.. code-block:: bash

    # Dump default config to have as reference
    python example.py --print_config > config.yaml
    # Modify the config as needed (all default settings can be removed)
    nano config.yaml
    # Run the tool using the adapted config
    python example.py --config config.yaml

Comparison to Fire
------------------

The :func:`.auto_cli` feature is similar to and inspired by `Fire
<https://pypi.org/project/fire/>`__. However, there are fundamental differences.
First, the purpose is not to allow calling any Python object from the command
line. It is only intended for running functions and classes specifically written
for this purpose. Second, the arguments are expected to have type hints, and the
given values will be validated according to these. Third, the return values of
the functions are not automatically printed. :func:`.auto_cli` returns the value
and it is up to the developer to decide what to do with it.


.. _tutorials:

Tutorials
=========

- `"jsonargparse - Say goodbye to configuration hassles"
  <https://2022.pycon.de/program/XK73C3/>`__  by Marianne Stecklina at PyCon DE
  & PyData Berlin 2022

    - Presentation video: https://youtu.be/2gDf2S0nHKg
    - GitHub repository: https://github.com/stecklin/pycon22-jsonargparse


.. _parsers:

Parsers
=======

An argument parser is created just like it is done with Python's `argparse
<https://docs.python.org/3/library/argparse.html>`__. You import the module,
create a parser object and then add arguments to it. A simple example would be:

.. testcode::

    from jsonargparse import ArgumentParser

    parser = ArgumentParser(prog="app", description="Description for my app.")
    parser.add_argument("--opt1", type=int, default=0, help="Help for option 1.")
    parser.add_argument("--opt2", type=float, default=1.0, help="Help for option 2.")


After creating the parser, you can use it to parse command line arguments with
the :meth:`parse_args <.ArgumentParser.parse_args>` function, after which you
get an object with the parsed values or defaults available as attributes. For
illustrative purposes giving to :meth:`parse_args <.ArgumentParser.parse_args>`
a list of arguments (instead of automatically getting them from the command line
arguments), with the parser shown above you would observe:

.. doctest::

    >>> cfg = parser.parse_args(["--opt2", "2.3"])
    >>> cfg.opt1, type(cfg.opt1)
    (0, <class 'int'>)
    >>> cfg.opt2, type(cfg.opt2)
    (2.3, <class 'float'>)

If the parsing fails the standard behavior is that the usage is printed and the
program is terminated. Alternatively you can initialize the parser with
``exit_on_error=False`` in which case an :class:`.ArgumentError` is raised.


Override order
--------------

Final parsed values depend on different sources, namely: source code, command
line arguments, :ref:`configuration-files` and :ref:`environment-variables`.
Values are overridden based on the following precedence:

1. Defaults defined in the source code.
2. Existing default config files in the order defined in
   ``default_config_files``, e.g. ``~/.config/myapp.yaml``.
3. Full config environment variable, e.g. ``APP_CONFIG``.
4. Individual key environment variables, e.g. ``APP_OPT1``.
5. Command line arguments in order left to right (might include config files).

Depending on the parse method used (see :class:`.ArgumentParser`) and how the
parser was built, some of the options above might not apply. Parsing of
environment variables must be explicitly enabled, except if using
:meth:`parse_env <.ArgumentParser.parse_env>`. If the parser does not have an
``action="config"`` argument, then there is no parsing of a full config
environment variable or a way to provide a config file from command line.


Capturing parsers
-----------------

It can be common practice to have a function that implements an entire CLI or a
function that constructs a parser conditionally based on some parameters and
then parses. For example, one might have:

.. testcode::

    from jsonargparse import ArgumentParser


    def main_cli():
        parser = ArgumentParser()
        ...
        cfg = parser.parse_args()
        ...


    if __name__ == "__main__":
        main_cli()

For some use cases it is necessary to get an instance of the parser object,
without doing any parsing. For instance `sphinx-argparse
<https://sphinx-argparse.readthedocs.io/en/stable/>`__ can be used to include
the help of CLIs in automatically generated documentation of a package. To use
sphinx-argparse it is necessary to have a function that returns the parser.
This can be easily implemented with :func:`.capture_parser` as follows:

.. testcode::

    from jsonargparse import capture_parser


    def get_parser():
        return capture_parser(main_cli)

.. note::

    The official way to obtain the parser for command line tools based on
    :func:`.auto_cli` is by using :func:`.auto_parser`, which is just a
    convenience function that calls :func:`.capture_parser`.


Optionals as positionals
------------------------

It can sometimes be useful to allow optional arguments to be passed both by
name, such as ``--key=val``, and as positional arguments, such as ``val``. This
behavior can be enabled by using
``set_parsing_settings(parse_optionals_as_positionals=True)``. Key points to
note about this feature are:

- Only optional arguments that accept exactly one value can be passed as
  positional, i.e., when ``nargs`` is not specified or is set to ``nargs=1``.
- Optional arguments with subclass types cannot be passed as positional
  arguments.
- Optionals are treated as positionals only after the standard positionals and
  in the order they were added to the parser. The usage section in the help
  displays the optionals that can be passed as positionals and their order.
- Optional arguments in parsers with subcommands cannot be passed as
  positionals. Only the child subparsers, after specifying the subcommand
  name(s), support this feature.

For instance, consider a parser defined as follows:

.. testcode::

    from jsonargparse import set_parsing_settings


    set_parsing_settings(parse_optionals_as_positionals=True)

    parser.add_argument("p1")
    parser.add_argument("--o2")
    parser.add_argument("--o3")

The help will display ``p1 [o2 [o3]]`` along with a note indicating that this
feature is enabled. Name-based parsing, such as ``--o2=val2 --o3=val3 val1``,
will work as expected. Additionally, the following cases are also valid:
``--o3=val3 val1 val2`` or ``val1 val2 val3``.

.. note::

    Positional arguments take precedence over optional arguments. This means
    that if a value is provided both as a positional and as an optional
    argument, the value from the positional argument will be used, regardless of
    the order. For example, with the parser above, the command ``val1 val2a
    --o2=val2b`` would result in ``o2=val2a``.


Always fail arguments
---------------------

In scenarios where an argument should be included in the parser but should
always fail parsing, there is the :class:`.ActionFail` action. For example a use
case can be an optional feature that is only accessible if a specific package is
installed:

.. testsetup:: always-fail

    parser = ArgumentParser()
    some_package_installed = False

.. testcode:: always-fail

    from jsonargparse import ActionFail

    if some_package_installed:
        parser.add_argument("--module", type=SomeClass)
    else:
        parser.add_argument(
            "--module",
            action=ActionFail(message="install 'package' to enable %(option)s"),
            help="Option unavailable due to missing 'package'",
        )

With this setup, if an argument is provided as ``--module=...`` or in a nested
form like ``--module.child=...``, the parsing will fail and display the
configured error message.


.. _unset-values:

Unset values
------------

By default, jsonargparse follows argparse behavior: an argument that is not
provided on the command line is given the value ``None`` in the parsed
namespace. This makes it impossible to distinguish between an argument that was
explicitly set to ``None`` (e.g. ``--opt=null``) and one that was simply
omitted.

The :obj:`.Unset` sentinel (enabled via
``set_parsing_settings(unset_sentinel=True)``) addresses this by using a
dedicated sentinel object as the default for arguments that have no explicitly
provided ``default`` value. The three possible states for an argument then
become:

- :obj:`.Unset` – the argument was not provided and no ``default`` was given in
  ``add_argument``.
- ``None`` – the argument was either explicitly set to ``null``, or its
  ``add_argument`` call included ``default=None``.
- Any other value – the argument was provided with that value (or defaults to
  it).

Example:

.. testcode:: unset-values

    from jsonargparse import ArgumentParser, Unset, set_parsing_settings

    set_parsing_settings(unset_sentinel=True)

    parser = ArgumentParser()
    parser.add_argument("--num", type=int | None)                 # no default given
    parser.add_argument("--flag", type=int | None, default=None)  # explicit None

    cfg = parser.parse_args([])
    assert cfg.num is Unset   # no default → Unset
    assert cfg.flag is None   # explicit default=None → None

    cfg = parser.parse_args(["--num=null"])
    assert cfg.num is None    # explicitly set to null

    cfg = parser.parse_args(["--num=5"])
    assert cfg.num == 5       # provided value

.. testcleanup:: docstrings

    set_parsing_settings(unset_sentinel=False)

The ``skip_unset`` parameter of :meth:`dump <.ArgumentParser.dump>`, :meth:`save
<.ArgumentParser.save>`, and :meth:`validate <.ArgumentParser.validate>`
controls whether :obj:`.Unset` entries are excluded. The
``--print_config=skip_unset`` flag does the same for command-line use.

**Relation to** ``argument_default=SUPPRESS``

Argparse's ``argument_default=SUPPRESS`` (and per-argument ``default=SUPPRESS``)
is a complementary mechanism: it causes an unprovided argument to be
**completely absent** from the parsed namespace, i.e. it has no key at all.
These two features play well together and represent different levels of
"absence".


.. _type-hints:

Type hints
==========

An important feature of jsonargparse is its wide support for argument types and
respective validation. This extended support makes use of Python's type hint
syntax. For example, an argument that can be ``None`` or a float in the range
``(0, 1)`` or a positive int could be added using a type hint as follows:

.. testcode::

    from jsonargparse.typing import PositiveInt, OpenUnitInterval

    parser.add_argument("--op", type=PositiveInt | OpenUnitInterval | None)

The types in :py:mod:`jsonargparse.typing` are included for convenience since
they are useful in argument parsing use cases and not available in standard
Python. However, there is no need to use jsonargparse specific types.

A wide range of type hints are supported and with arbitrary complexity/nesting.
Some notes about this support are:

- Nested types are supported as long as at least one child type is supported. By
  nesting it is meant child types inside ``list``, ``dict``, etc. There is no
  limit in nesting depth.

- Postponed evaluation of types PEP `563 <https://peps.python.org/pep-0563/>`__
  (i.e. ``from __future__ import annotations``) is supported. Also supported are
  PEP `585 <https://peps.python.org/pep-0585/>`__ (i.e. ``list[<type>],
  dict[<type>], ...`` instead of ``List[<type>], Dict[<type>], ...``) and `604
  <https://peps.python.org/pep-0604/>`__ (i.e. ``<type> | <type>`` instead of
  ``Union[<type>, <type>]``).

- Types that use components imported inside ``TYPE_CHECKING`` blocks are
  supported.

- Resolving of forward references in types is supported.

- Fully supported types are: ``str``, ``bool`` (more details in
  :ref:`boolean-arguments`), ``int``, ``float``, ``Decimal``, ``complex``,
  ``bytes``/``bytearray`` (Base64 encoding), ``range``, ``list`` (more details
  in :ref:`list-append`), ``Deque``, ``Iterable``, ``Sequence``, ``Any``,
  ``Union``, ``Optional``, ``Type``, ``Enum``, ``PathLike``, ``UUID``,
  ``timedelta``, restricted types as explained in sections
  :ref:`restricted-numbers` and :ref:`restricted-strings` and path and URL types
  as explained in sections :ref:`parsing-paths` and :ref:`parsing-urls`.

- ``dict``, ``Mapping``, ``MutableMapping``, ``MappingProxyType``,
  ``OrderedDict``, and ``TypedDict`` are supported but only with ``str`` or
  ``int`` keys. ``Required`` and ``NotRequired`` are also supported for
  fine-grained specification of required/optional ``TypedDict`` keys.
  ``Unpack`` is supported with ``TypedDict`` for more precise ``**kwargs``
  typing as described in PEP `692 <https://peps.python.org/pep-0692/>`__.
  For more details see :ref:`dict-items`.

- ``tuple``, ``set``, ``frozenset`` and ``MutableSet`` are supported even though
  they can't be represented in JSON distinguishable from a list. Each ``tuple``
  element position can have its own type and will be validated as such.
  ``tuple`` with ellipsis (``tuple[type, ...]``) is also supported. In command
  line arguments, config files and environment variables, tuples and sets are
  represented as an array.

- To set a value to ``None`` it is required to use ``null`` since this is how
  JSON/YAML defines it. To avoid confusion in the help, ``NoneType`` is
  displayed as ``null``. For example a function argument with type and default
  ``Optional[str] = None`` would be shown in the help as ``type: Union[str,
  null], default: null``.

- Normal classes can be used as a type, which are specified with a dict
  containing ``class_path`` and optionally ``init_args``. :meth:`instantiate
  <.ArgumentParser.instantiate>` can be used to instantiate all classes in a
  config object. For more details see :ref:`sub-classes`.

- ``Protocol`` types are also supported the same as subclasses. The protocols
  are not required to be ``runtime_checkable``. But the accepted classes must
  implement all of the protocol's public methods with a compatible signature,
  i.e. the methods must be callable in all the ways that the protocol's methods
  can be called, similar to what static type checkers verify. Parameter and
  return types must match exactly, subtypes are not accepted, except when the
  protocol has no annotation or ``Any``, which accept any type.

- ``dataclasses``, final classes, attrs' ``define``, pydantic's ``dataclass``
  and pydantic's ``BaseModel`` are supported even when nested. By default they
  don't accept subclasses. For more details see :ref:`subclasses-disabled` and
  for enabling subclasses see :ref:`enable-disable-subclasses`. If a dataclass
  is mixed inheriting from a normal class, by default subclasses are accepted.

- User-defined ``Generic`` types are supported. For more details see
  :ref:`generic-types`.

- ``Annotated`` types are supported. If the metadata corresponds to a `pydantic
  type <https://docs.pydantic.dev/latest/api/types/>`__, this is used for
  validation.

- ``pydantic.SecretStr`` type is supported with the expected behavior of not
  serializing the actual value. There is also ``jsonargparse.typing.SecretStr``
  to support the same behavior without the need of a dependency.

- ``pydantic.FilePath`` and ``pydantic.DirectoryPath`` types are supported,
  running the corresponding pydantic validation when parsing. Arguments with
  these types also get file and directory tab completions, see
  :ref:`tab-completion`.

- ``Callable`` is supported by either giving a dot import path to a callable
  object or by giving a dict with a ``class_path`` and optionally ``init_args``
  entries. The specified class must either instantiate into a callable or be a
  subclass of the return type of the callable. For these cases running
  :meth:`instantiate <.ArgumentParser.instantiate>` will instantiate the class
  or provide a function that returns the instance of the class. For more details
  see :ref:`callable-type`. Currently the callable's argument and return types
  are not validated.

- ``TypeAliasType`` is supported with values parsed as the aliased type and the
  alias shown as the argument type in help.


.. _restricted-numbers:

Restricted numbers
------------------

It is quite common that when parsing a number, its range should be limited. To
ease these cases the module ``jsonargparse.typing`` includes some predefined
types and a function :func:`.restricted_number_type` to define new types. The
predefined types are: :class:`.PositiveInt`, :class:`.NonNegativeInt`,
:class:`.PositiveFloat`, :class:`.NonNegativeFloat`,
:class:`.ClosedUnitInterval` and :class:`.OpenUnitInterval`. Examples of usage
are:

.. testcode::

    from jsonargparse.typing import PositiveInt, PositiveFloat, restricted_number_type

    # float larger than zero
    parser.add_argument("--op1", type=PositiveFloat)
    # between 0 and 10
    from_0_to_10 = restricted_number_type("from_0_to_10", int, [(">=", 0), ("<=", 10)])
    parser.add_argument("--op2", type=from_0_to_10)


.. _restricted-strings:

Restricted strings
------------------

Similar to the restricted numbers, there is a function to create string types
that are restricted to match a given regular expression:
:func:`.restricted_string_type`. A predefined type is :class:`.Email` which is
restricted so that it follows the normal email pattern. For example to add an
argument required to be exactly four uppercase letters:

.. testcode::

    from jsonargparse.typing import Email, restricted_string_type

    CodeType = restricted_string_type("CodeType", "^[A-Z]{4}$")
    parser.add_argument("--code", type=CodeType)
    parser.add_argument("--email", type=Email)


.. _parsing-paths:

Parsing paths
-------------

For some use cases it is necessary to parse file paths, checking its existence
and access permissions, but not necessarily opening the file. Moreover, a file
path could be included in a config file as relative with respect to the config
file's location. After parsing it should be easy to access the parsed file path
without having to consider the location of the config file. To help in these
situations jsonargparse includes a type generator :func:`.path_type`, some
predefined types (e.g. :class:`.Path_fr`).

For example suppose you have a directory with a config file ``app/config.yaml``
and some data ``app/data/info.db``. The contents of the YAML file is the
following:

.. code-block:: yaml

    # File: config.yaml
    databases:
      info: data/info.db

To create a parser that checks that the value of ``databases.info`` is a file
that exists and is readable, the following could be done:

.. testsetup:: paths

    cwd = os.getcwd()
    tmpdir = tempfile.mkdtemp(prefix="_jsonargparse_doctest_")
    os.chdir(tmpdir)
    os.mkdir("app")
    os.mkdir("app/data")
    with open("app/config.yaml", "w") as f:
        f.write("databases:\n  info: data/info.db\n")
    with open("app/data/info.db", "w") as f:
        f.write("info\n")

.. testcleanup:: paths

    os.chdir(cwd)
    shutil.rmtree(tmpdir)

.. testcode:: paths

    from jsonargparse import ArgumentParser
    from jsonargparse.typing import Path_fr

    parser = ArgumentParser()
    parser.add_argument("--databases.info", type=Path_fr)
    cfg = parser.parse_path("app/config.yaml")

The ``fr`` in the type are flags that stand for file and readable. After
parsing, the value of ``databases.info`` will be an instance of the
:class:`.Path_fr` class that allows to get both the original relative path as
included in the YAML file, or the corresponding absolute path:

.. doctest:: paths
    :skipif: os.name != "posix"

    >>> cfg.databases.info.relative
    'data/info.db'
    >>> cfg.databases.info.absolute  # doctest: +ELLIPSIS
    '/.../app/data/info.db'

Likewise directories can be parsed using the :class:`.Path_dw` type, which would
require a directory to exist and be writable. New path types can be created
using the :func:`.path_type` function. For example to create a type for files
that must exist and be both readable and writable, the command would be
``Path_frw = path_type('frw')``. If the file ``app/config.yaml`` is not
writable, then using the type to cast ``Path_frw('app/config.yaml')`` would
raise a *TypeError: File is not writable* exception. For more information of
all the mode flags supported, refer to the documentation of the :class:`.Path`
class.

Types created with :func:`.path_type` have as base class  :class:`.Path`. This
class implements the ``os.PathLike`` protocol, using the absolute version as the
actual path, thus for the previous example:

.. doctest:: paths
    :skipif: os.name != "posix"

    >>> os.fspath(cfg.databases.info)  # doctest: +ELLIPSIS
    '/.../app/data/info.db'

The content of a file referenced by a :class:`.Path` instance can be read using
the :py:meth:`.Path.read_text` method. For the previous example, this would be
``info_db = cfg.databases.info.read_text()``.

An argument with a path type can be given ``nargs='+'`` to parse multiple paths.
Thus, from command line you could do ``--files file1 file2``, separated by
space. It might also be desired to parse a list of paths found in a plain text
file or from stdin. For this add the argument with type ``list[<path_type>]``
and ``sub_configs=True``. To read from stdin give the special string ``'-'``.
Example:

.. testsetup:: path_list

    cwd = os.getcwd()
    tmpdir = tempfile.mkdtemp(prefix="_jsonargparse_doctest_")
    os.chdir(tmpdir)
    pathlib.Path("paths.lst").write_text("paths.lst\n")
    pathlib.Path("file1").touch()
    pathlib.Path("file2").touch()

    parser = ArgumentParser()

    stdin = sys.stdin
    sys.stdin = StringIO("paths.lst\n")

.. testcleanup:: path_list

    sys.stdin = stdin
    os.chdir(cwd)
    shutil.rmtree(tmpdir)

.. testcode:: path_list

    from jsonargparse.typing import Path_fr

    parser.add_argument("--list", type=list[Path_fr], sub_configs=True)
    cfg = parser.parse_args(["--list", "paths.lst"])  # File with list of paths
    cfg = parser.parse_args(["--list", "-"])  # List of paths from stdin

In this case since there is no ``nargs``, the argument expects a single value.
That is why to provide multiple paths directly from command line, a more
cumbersome YAML/JSON array syntax is required, i.e. ``--list "[file1,file2]"``.
However, the simpler syntax described in :ref:`list-append` can also be used,
which would be like ``--list+ file1 --list+ file2``. Not as simple as with
``nargs='+'`` but with tab completion enabled the effort is minimal.

The same ``list[<path_type>]`` behavior described here will work for arguments
automatically created from type hints in signatures, that is with
:func:`.auto_cli`, :meth:`add_function_arguments
<.ArgumentParser.add_function_arguments>`, :meth:`add_method_arguments
<.ArgumentParser.add_method_arguments>`, :meth:`add_class_arguments
<.ArgumentParser.add_class_arguments>` and :meth:`add_subclass_arguments
<.ArgumentParser.add_subclass_arguments>`.

.. note::

    If ``nargs='+'`` and ``sub_configs=True`` are set for an argument of type
    ``list[<path_type>]``, each argument will produce a list of paths. This
    behavior may not be what you expect.

.. note::

    Not all features of the :class:`.Path` class are supported on Windows.


.. _parsing-urls:

Parsing URLs
------------

The :func:`.path_type` function also supports URLs which after parsing, the
:py:meth:`.Path.read_text` method can be used to perform a GET request to the
corresponding URL and retrieve its content. For this to work the *requests*
Python package is required. Alternatively, :func:`.path_type` can also be used
for `fsspec <https://filesystem-spec.readthedocs.io>`__ supported file systems.
The respective optional package(s) will be installed along with jsonargparse if
installed with the ``urls`` or ``fsspec`` extras as explained in section
:ref:`installation`.

The ``'u'`` flag is used to parse URLs using requests and the flag ``'s'`` to
parse fsspec file systems. For example if it is desired that an argument can be
either a readable file or URL, the type would be created as ``Path_fur =
path_type('fur')``. If the value appears to be a URL, a HEAD request would be
triggered to check if it is accessible. To get the content of the parsed path,
without needing to care if it is a local file or a URL, the
:py:meth:`.Path.read_text` method can be used.

If you import ``from jsonargparse import set_parsing_settings`` and then run
``set_parsing_settings(config_read_mode_urls_enabled=True)`` or
``set_parsing_settings(config_read_mode_fsspec_enabled=True)``, the following
functions and classes will also support loading from URLs: :meth:`parse_path
<.ArgumentParser.parse_path>`, :meth:`get_defaults
<.ArgumentParser.get_defaults>` (``default_config_files`` argument),
``action="config"``, :py:meth:`.FromConfigMixin.from_config`,
:class:`.ActionJsonSchema`, :class:`.ActionJsonnet` and :class:`.ActionParser`.
This means that a tool that can receive a config file via ``action="config"`` is
able to get the content from a URL, thus something like the following would
work:

.. code-block:: bash

    my_tool.py --config http://example.com/config.yaml

.. note::

    Relative paths inside a remote path are parsed as remote. For example, for a
    relative path ``model/state_dict.pt`` found inside
    ``s3://bucket/config.yaml``, its parsed absolute path becomes
    ``s3://bucket/model/state_dict.pt``.


.. _boolean-arguments:

Booleans
--------

Parsing boolean arguments is very common, however, the original argparse only
has a limited support for them, via ``store_true`` and ``store_false``.
Furthermore unexperienced users might mistakenly use ``type=bool`` which would
not provide the intended behavior.

With jsonargparse adding an argument with ``type=bool`` the intended action is
implemented. If given as values ``{'yes', 'true'}`` or ``{'no', 'false'}`` the
corresponding parsed values would be ``True`` or ``False``. For example:

.. testsetup:: boolean

    parser = ArgumentParser()

.. doctest:: boolean

    >>> parser.add_argument("--op1", type=bool, default=False)  # doctest: +IGNORE_RESULT
    >>> parser.add_argument("--op2", type=bool, default=True)  # doctest: +IGNORE_RESULT
    >>> parser.parse_args(["--op1", "yes", "--op2", "false"])
    Namespace(op1=True, op2=False)

Sometimes it is also useful to define two paired options, one to set ``True``
and the other to set ``False``. The :class:`.ActionYesNo` class makes this
straightforward. A couple of examples would be:

.. testsetup:: yes_no

    parser = ArgumentParser()

.. testcode:: yes_no

    from jsonargparse import ActionYesNo

    # --opt1 for true and --no_opt1 for false.
    parser.add_argument("--op1", action=ActionYesNo)
    # --with-opt2 for true and --without-opt2 for false.
    parser.add_argument("--with-op2", action=ActionYesNo(yes_prefix="with-", no_prefix="without-"))

If the :class:`.ActionYesNo` class is used in conjunction with ``nargs='?'`` the
options can also be set by giving as value any of ``{'true', 'yes', 'false',
'no'}``.


.. _enums:

Enum arguments
--------------

Another case of restricted values is string choices. In addition to the common
``choices`` given as a list of strings, it is also possible to provide as type
an ``Enum`` class. This has the added benefit that strings are mapped to some
desired values. For example:

.. testsetup:: enum

    parser = ArgumentParser()

.. doctest:: enum

    >>> import enum
    >>> class MyEnum(enum.Enum):
    ...     choice1 = -1
    ...     choice2 = 0
    ...     choice3 = 1
    ...
    >>> parser.add_argument("--op", type=MyEnum)  # doctest: +IGNORE_RESULT
    >>> parser.parse_args(["--op=choice1"])
    Namespace(op=<MyEnum.choice1: -1>)


.. _list-append:

List append
-----------

As detailed before, arguments with ``list`` type are supported. By default when
specifying an argument value, the previous value is replaced, and this also
holds for lists. Thus, a parse such as ``parser.parse_args(['--list=[1]',
'--list=[2, 3]'])`` would result in a final value of ``[2, 3]``. However, in
some cases it might be decided to append to the list instead of replacing. This
can be achieved by adding ``+`` as suffix to the argument key, for example:

.. testsetup:: append

    parser = ArgumentParser()


    class MyBaseClass:
        pass

.. doctest:: append

    >>> parser.add_argument("--list", type=list[int])  # doctest: +IGNORE_RESULT
    >>> parser.parse_args(["--list=[1]", "--list+=[2, 3]"])
    Namespace(list=[1, 2, 3])
    >>> parser.parse_args(["--list=[4]", "--list+=5"])
    Namespace(list=[4, 5])

Append is also supported in config files. For instance the following two config
files would first assign a list and then append to this list:

.. code-block:: yaml

    # config1.yaml
    list:
    - 1

.. code-block:: yaml

    # config2.yaml
    list+:
    - 2
    - 3

Appending works for any type for the list elements. Lists with class type
elements (see :ref:`sub-classes`) are also supported. To append to the list,
first append a new class by using the ``+`` suffix. Then ``init_args`` for this
class are specified like if the type wasn't a list, since the arguments are
applied to the last class in the list. Take for example that an argument is
added to a parser as:

.. testcode:: append

    parser.add_argument("--list_of_instances", type=list[MyBaseClass])

Thanks to the short notation, command line arguments don't require to specify
``class_path`` and ``init_args``. Thus, multiple classes can be appended and its
arguments set as follows:

.. code-block:: bash

    python tool.py \
      --list_of_instances+={CLASS_1_PATH} \
      --list_of_instances.{CLASS_1_ARG_1}=... \
      --list_of_instances.{CLASS_1_ARG_2}=... \
      --list_of_instances+={CLASS_2_PATH} \
      --list_of_instances.{CLASS_2_ARG_1}=... \
      ...
      --list_of_instances+={CLASS_N_PATH} \
      --list_of_instances.{CLASS_N_ARG_1}=... \
      ...

Once a new class has been appended to the list, it is not possible to modify the
arguments of a previous class. This limitation is intentional since it forces
classes and its arguments to be defined in order, making the command line call
intuitive to write and understand.


.. _dict-items:

Dict items
----------

When an argument has ``dict`` as type, the value can be set using JSON format,
e.g.:

.. testsetup:: dict_items

    parser = ArgumentParser()

.. doctest:: dict_items

    >>> parser.add_argument("--dict", type=dict)  # doctest: +IGNORE_RESULT
    >>> parser.parse_args(['--dict={"key1": "val1", "key2": "val2"}'])
    Namespace(dict={'key1': 'val1', 'key2': 'val2'})

Similar to lists, providing a second argument with value a JSON dict completely
replaces the previous value. Setting individual dict items without replacing can
be achieved as follows:

.. doctest:: dict_items

    >>> parser.parse_args(["--dict.key1=val1", "--dict.key2=val2"])
    Namespace(dict={'key1': 'val1', 'key2': 'val2'})


.. _generic-types:

Generic types
-------------

Classes that inherit from ``typing.Generic``, also known as `user-defined
generic types
<https://docs.python.org/3/library/typing.html#user-defined-generic-types>`__,
are supported. Take for example a point in 2D:

.. testsetup:: generic_types

    parser = ArgumentParser()

.. testcode:: generic_types

    from typing import Generic, TypeVar

    Number = TypeVar("Number", float, complex)

    @dataclass
    class Point2d(Generic[Number]):
        x: Number = 0.0
        y: Number = 0.0

Parsing complex-valued points would be:

.. doctest:: generic_types

    >>> parser.add_argument("--point", type=Point2d[complex])  # doctest: +IGNORE_RESULT
    >>> parser.parse_args(["--point.x=(1+2j)"]).point
    Namespace(x=(1+2j), y=0.0)


.. _callable-type:

Callable type
-------------

When using ``Callable`` as type, the parser accepts several options. The first
option is the import path of a callable object, for example:

.. testsetup:: callable

    parser = ArgumentParser()

.. testcode:: callable

    parser.add_argument("--callable", type=Callable)
    parser.parse_args(["--callable=time.sleep"])

A second option is a class that once instantiated becomes callable:

.. testcode:: callable

    class OffsetSum:
        def __init__(self, offset: int):
            self.offset = offset

        def __call__(self, value: int):
            return self.offset + value

.. testcode:: callable
    :hide:

    doctest_mock_class_in_main(OffsetSum)

.. doctest:: callable

    >>> value = {
    ...     "class_path": "__main__.OffsetSum",
    ...     "init_args": {
    ...         "offset": 3,
    ...     },
    ... }

    >>> cfg = parser.parse_args(["--callable", str(value)])
    >>> cfg.callable
    Namespace(class_path='__main__.OffsetSum', init_args=Namespace(offset=3))
    >>> init = parser.instantiate(cfg)
    >>> init.callable(5)
    8

The third option is only applicable when the type is a callable that returns
class instances. This is a form of :ref:`dependency-injection`, so this third
case is explained in section :ref:`instance-factories`.

.. _registering-types:

Registering types
-----------------

With the :func:`.register_type` function it is possible to register additional
types for use in jsonargparse parsers. If the type class can be instantiated
with a string representation and casting the instance to ``str`` gives back the
string representation, then only the type class is given to
:func:`.register_type`. For example in the ``jsonargparse.typing`` package this
is how complex numbers are registered: ``register_type(complex)``. For other
type classes that don't have these properties, to register it might be necessary
to provide a serializer and/or deserializer function. Including the serializer
and deserializer functions, the registration of the complex numbers example is
equivalent to ``register_type(complex, serializer=str, deserializer=complex)``.

A more useful example could be registering the ``datetime`` class. This case
requires to give both a serializer and a deserializer as seen below.

.. testcode::

    from datetime import datetime
    from jsonargparse import ArgumentParser
    from jsonargparse.typing import register_type


    def serializer(v):
        return v.isoformat()


    def deserializer(v):
        return datetime.strptime(v, "%Y-%m-%dT%H:%M:%S")


    register_type(datetime, serializer, deserializer)

    parser = ArgumentParser()
    parser.add_argument("--datetime", type=datetime)
    parser.parse_args(["--datetime=2008-09-03T20:56:35"])

.. note::

    The registering of types is only intended for simple types. By default any
    class used as a type hint is considered a subclass (see :ref:`sub-classes`)
    which might be good for many use cases. If a class is registered with
    :func:`.register_type` then the subclass option is no longer available.


.. _custom-types:

Creating custom types
---------------------

It is possible to create new types and use them for parsing. Even though types
can be created for specific CLI behaviors, it is recommended to create them such
that they make sense independent of parsing. This is so that they can be used as
type hints in functions and classes in order to improve the code in a more
general sense. An alternative to creating types, can be to use `pydantic types
<https://docs.pydantic.dev/latest/api/types/>`__.

There are a few ways for creating types, the most simple being to implement a
class. When creating a type, take as reference how basic types work, e.g.
``int``. Properties of basic types are:

- Casting a string creates an instance of the type, if the value is valid, e.g.
  ``int("1")``.
- Casting a string raises a ``ValueError``, if the value is not valid, e.g.
  ``int("a")``.
- Casting an instance of the type to string gives back the string representation
  of the value, e.g. ``str(1) == "1"``.
- Types are idempotent, i.e. casting an instance of the type to the type gives
  back the same value, e.g. ``int(1) == int(int(1))``.

Once a type is created, it can be registered with :func:`.register_type`. If the
type follows the properties above, then there is no need to provide more
parameters, just do ``register_type(MyType)``.

The :func:`.extend_base_type` function can be useful for creating and
registering new types in a single call. For example, creating a type for even
integers could be done as:

.. testcode::

    from jsonargparse.typing import extend_base_type

    def is_even(class_type, value):
        if int(value) % 2 != 0:
            raise ValueError(f"{value} is not even")

    EvenInt = extend_base_type("EvenInt", int, is_even)

Then this type can be used in a parser as:

.. doctest::

    >>> parser = ArgumentParser()
    >>> parser.add_argument("--even_int", type=EvenInt)  # doctest: +IGNORE_RESULT
    >>> parser.parse_args(["--even_int=2"])
    Namespace(even_int=2)

When using custom types as a type hint, defaults must be casted so that static
type checkers don't complain. For example:

.. testcode::

    def fn(value: EvenInt = EvenInt(2)):
        ...


.. _nested-namespaces:

Nested namespaces
=================

A difference with respect to basic argparse is, that by using dot notation in
the argument names, you can define a hierarchy of nested namespaces. For example
you could do the following:

.. doctest::

    >>> parser = ArgumentParser(prog="app")
    >>> parser.add_argument("--lev1.opt1", default="from default 1")  # doctest: +IGNORE_RESULT
    >>> parser.add_argument("--lev1.opt2", default="from default 2")  # doctest: +IGNORE_RESULT
    >>> cfg = parser.get_defaults()
    >>> cfg.lev1.opt1
    'from default 1'
    >>> cfg.lev1.opt2
    'from default 2'

A group of nested options can be created by using a dataclass. This has the
advantage that the same options can be reused in multiple places of a project.
An example analogous to the one above would be:

.. testcode::

    from dataclasses import dataclass


    @dataclass
    class Level1Options:
        """Level 1 options
        Args:
            opt1: Option 1
            opt2: Option 2
        """

        opt1: str = "from default 1"
        opt2: str = "from default 2"


    parser = ArgumentParser()
    parser.add_argument("--lev1", type=Level1Options, default=Level1Options())

The :class:`.Namespace` class is an extension of the one from argparse, having
some additional features. In particular, keys can be accessed like a dictionary
either with individual keys, e.g. ``cfg['lev1']['opt1']``, or a single one, e.g.
``cfg['lev1.opt1']``. Also the class has a method :py:meth:`.Namespace.as_dict`
that can be used to represent the nested namespace as a nested dictionary. This
is useful for example for class instantiation.


.. _configuration-files:

Configuration files
===================

An important feature of jsonargparse is its ability to parse configuration files
(config files). The dot notation hierarchy of the arguments (see
:ref:`nested-namespaces`) defines the expected structure in these files. By
default, the configuration format is YAML. To change the format, use the
``parser_mode`` parameter when instantiating the parser, e.g.,
``ArgumentParser(parser_mode="toml")``.

The :py:attr:`.ArgumentParser.default_config_files` property can be set when
creating a parser to specify patterns for searching config files. For example,
if a parser is created as
``ArgumentParser(default_config_files=['~/.myapp.yaml', '/etc/myapp.yaml'])``,
it will search for and parse any of these files if they exist, using them to
override the defaults. All matched config files are parsed and applied in the
given order. The default config files are always parsed first, meaning any
command line argument will override their values.

You can also add an argument to explicitly provide a config file path. Providing
a config file as an argument does not disable the parsing of
``default_config_files``. The config argument will be parsed in the specific
position among the command line arguments, so arguments found afterward will
override the values from that config file. The config argument can be given
multiple times, each instance overriding the values of the previous one. Using
the example parser from the :ref:`nested-namespaces` section above, we could
have the following config file in YAML format:

.. code-block:: yaml

    # File: example.yaml
    lev1:
      opt1: from yaml 1
      opt2: from yaml 2

Then in Python adding a config file argument and parsing some dummy arguments,
the following would be observed:

.. testsetup:: config

    cwd = os.getcwd()
    tmpdir = tempfile.mkdtemp(prefix="_jsonargparse_doctest_")
    os.chdir(tmpdir)
    with open("example.yaml", "w") as f:
        f.write("lev1:\n  opt1: from yaml 1\n  opt2: from yaml 2\n")

.. testcleanup:: config

    os.chdir(cwd)
    shutil.rmtree(tmpdir)

.. doctest:: config

    >>> from jsonargparse import ArgumentParser
    >>> parser = ArgumentParser()
    >>> parser.add_argument("--lev1.opt1", default="from default 1")  # doctest: +IGNORE_RESULT
    >>> parser.add_argument("--lev1.opt2", default="from default 2")  # doctest: +IGNORE_RESULT
    >>> parser.add_argument("--config", action="config")  # doctest: +IGNORE_RESULT
    >>> cfg = parser.parse_args(["--lev1.opt1", "from arg 1", "--config", "example.yaml", "--lev1.opt2", "from arg 2"])
    >>> cfg.lev1.opt1
    'from yaml 1'
    >>> cfg.lev1.opt2
    'from arg 2'

Instead of providing a path to a config file, a string with the config content
can also be provided.

.. doctest:: config

    >>> cfg = parser.parse_args(["--config", '{"lev1":{"opt1":"from string 1"}}'])
    >>> cfg.lev1.opt1
    'from string 1'

The config file can also be provided as an environment variable as explained in
section :ref:`environment-variables`. The config file environment variable is
the first one to be parsed. Any other argument provided through an environment
variable would override the config file one.

A config file or string can also be parsed without parsing command line
arguments. The methods for this are :meth:`parse_path
<.ArgumentParser.parse_path>` and :meth:`parse_string
<.ArgumentParser.parse_string>` to parse a config file or a config string
respectively.

Serialization
-------------

Parsers that have an ``action="config"`` argument also include a
``--print_config`` option. This is useful particularly for command line tools
with a large set of options to create an initial config file including all
default values. If the `ruamel.yaml <https://pypi.org/project/ruamel.yaml>`__
package is installed, the config can be printed having the help descriptions
content as YAML comments by using ``--print_config=comments``. The comments
include the descriptions of the groups and arguments of the parser, and for
values that correspond to a class, e.g. the ``init_args`` of a subclass or the
fields of a dataclass, the descriptions from the respective class. Another
option is ``--print_config=skip_unset`` which skips entries whose value is the
configured unset value (see :ref:`unset-values`).

From within Python it is also possible to serialize a config object by using
either the :meth:`dump <.ArgumentParser.dump>` or :meth:`save
<.ArgumentParser.save>` parser methods. Several formats with a particular style
are supported: ``yaml``, ``toml``, ``json_compact`` and ``json_indented``. It is
possible to add more dumping formats by using the :func:`.set_dumper` function.
For example to allow dumping using PyYAML's ``default_flow_style`` do the
following:

.. testcode::

    import yaml
    from jsonargparse import set_dumper


    def custom_yaml_dump(data):
        return yaml.safe_dump(data, default_flow_style=True)


    set_dumper("yaml_custom", custom_yaml_dump)

.. _custom-loaders:

Custom loaders
--------------

The ``yaml`` parser mode (see :py:meth:`.ArgumentParser.__init__`) uses for
loading a subclass of `yaml.SafeLoader
<https://pyyaml.org/wiki/PyYAMLDocumentation#loader>`__ with two modifications.
First, it supports float's scientific notation, e.g. ``'1e-3' => 0.001`` (unlike
default PyYAML which considers ``'1e-3'`` a string). Second, text within curly
braces is considered a string, e.g. ``'{text}' (unlike default PyYAML which
parses this as ``{'text': None}``).

It is possible to replace the ``yaml`` loader or add a loader as a new parser
mode via the :func:`.set_loader` function. For example if you need a custom
PyYAML loader it can be registered and used as follows:

.. testcode::

    import yaml
    from jsonargparse import ArgumentParser, set_loader


    class CustomLoader(yaml.SafeLoader):
        ...


    def custom_yaml_load(stream):
        return yaml.load(stream, Loader=CustomLoader)


    set_loader("yaml_custom", custom_yaml_load)

    parser = ArgumentParser(parser_mode="yaml_custom")

When setting a loader based on a library different from PyYAML, the ``exceptions``
that it raises when there are failures should be given to :func:`.set_loader`.


.. _classes-methods-functions:

Classes, methods and functions
==============================

It is good practice to write Python code in which parameters have type hints and
these are described in the docstrings. To make this well written code
configurable, it wouldn't make sense to duplicate information of types and
parameter descriptions. To avoid this duplication, jsonargparse includes methods
to automatically add annotated parameters as arguments, see
:meth:`add_function_arguments <.ArgumentParser.add_function_arguments>`,
:meth:`add_method_arguments <.ArgumentParser.add_method_arguments>`,
:meth:`add_class_arguments <.ArgumentParser.add_class_arguments>` and
:meth:`add_subclass_arguments <.ArgumentParser.add_subclass_arguments>`.

Take for example a class with its init and a method with docstrings as follows:

.. testsetup:: class_method

    sys.argv = ["", "--myclass.init.foo={}", "--myclass.method.bar=0"]


    class MyBaseClass:
        pass

.. testcode:: class_method

    class MyClass(MyBaseClass):
        def __init__(self, foo: dict[str, int | list[int]], **kwargs):
            """Initializer for MyClass.

            Args:
                foo: Description for foo.
            """
            super().__init__(**kwargs)
            ...

        def mymethod(self, bar: float, baz: bool = False):
            """Description for mymethod.

            Args:
                bar: Description for bar.
                baz: Description for baz.
            """
            ...

Both ``MyClass`` and ``mymethod`` can easily be made configurable, the class
initialized and the method executed as follows:

.. testcode:: class_method

    from jsonargparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_class_arguments(MyClass, "myclass.init")
    parser.add_method_arguments(MyClass, "mymethod", "myclass.method")

    cfg = parser.parse_args()
    myclass = MyClass(**cfg.myclass.init.as_dict())
    myclass.mymethod(**cfg.myclass.method.as_dict())


The :meth:`add_class_arguments <.ArgumentParser.add_class_arguments>` call adds
to the ``myclass.init`` key the ``items`` argument with description as in the
docstring, sets it as required since it lacks a default value. When parsed, it
is validated according to the type hint, i.e., a dict with values ints or list
of ints. Also since the init has the ``**kwargs`` argument, the keyword
arguments from ``MyBaseClass`` are also added to the parser. Similarly, the
:meth:`add_method_arguments <.ArgumentParser.add_method_arguments>` call adds to
the ``myclass.method`` key, the arguments ``value`` as a required float and
``flag`` as an optional boolean with default value false.


Instantiation of several classes added with :meth:`add_class_arguments
<.ArgumentParser.add_class_arguments>` can be done more simply for an entire
config object using :meth:`instantiate <.ArgumentParser.instantiate>`. For the
example above running ``cfg = parser.instantiate(cfg)`` would result in
``cfg.myclass.init`` containing an instance of ``MyClass`` initialized with
whatever command line arguments were parsed.

When parsing from a config file (see :ref:`configuration-files`) all the values
can be given in a single config file. For convenience it is also possible that
the values for each of the argument groups created by the calls to add
signatures methods can be parsed from independent files. This means that for the
example above there could be one general config file with contents:

.. code-block:: yaml

    myclass:
      init: myclass.yaml
      method: mymethod.yaml

Then the files ``myclass.yaml`` and ``mymethod.yaml`` would include the settings
for the instantiation of the class and the call to the method respectively.

A wide range of type hints are supported for the signature parameters. For exact
details go to section :ref:`type-hints`. Some notes about the add signature
methods are:

- All positional only parameters must have a type, otherwise the add arguments
  functions raise an exception.

- Keyword parameters are ignored if they don't have at least one type that is
  supported.

- Parameters whose name starts with ``_`` are considered internal and ignored.

- The signature methods have a ``skip`` parameter which can be used to exclude
  adding some arguments, e.g. ``parser.add_method_arguments(MyClass, 'mymethod',
  skip={'flag'})``.

.. note::

    The signatures support is intended to be non-intrusive. It is by design that
    there is no need to inherit from a class, add decorators, or use special
    type hints and default values. This has several advantages. For example it
    is possible to use classes from third party libraries which is not possible
    for developers to modify.

From config mixin
-----------------

For classes that should support direct instantiation from configuration values,
:class:`.FromConfigMixin` adds a ``from_config`` class method. It can be useful
for small utilities that need to load constructor values from a dictionary or a
configuration file in one call.

.. doctest::

    >>> from jsonargparse import FromConfigMixin
    >>> class Client(FromConfigMixin):
    ...     def __init__(self, host: str = "localhost", port: int = 80):
    ...         self.host = host
    ...         self.port = port
    >>> client = Client.from_config({"host": "api.local", "port": 8080})
    >>> (client.host, client.port)
    ('api.local', 8080)

For details on all supported behavior, see :class:`.FromConfigMixin` in the API
reference.

Docstring parsing
-----------------

To get parameter docstrings in the parser help, the `docstring-parser
<https://pypi.org/project/docstring-parser/>`__ package is required. This
package is included when installing jsonargparse with the ``signatures`` extra
as explained in section :ref:`installation`.

A couple of options can be configured, both related to docstring parsing speed.
By default docstrings are parsed used with
``docstring_parser.DocstringStyle.AUTO``, which means that it is attempted to
parse docstrings with all supported styles. If the relevant codebase uses a
single style, this is inefficient. A single style can be configured as follows:

.. testcode:: docstrings

    from docstring_parser import DocstringStyle
    from jsonargparse import set_parsing_settings

    set_parsing_settings(docstring_parse_style=DocstringStyle.REST)

The second option that can be configured is the support for `attribute
docstrings <https://peps.python.org/pep-0257/#what-is-a-docstring>`__ (i.e.
literal strings in the line after an attribute is defined). By default this
feature is disabled and enabling it makes the parsing slower even for classes
that don't have attribute docstrings. To enable this, do as follows:

.. testcode:: docstrings

    from dataclasses import dataclass
    from jsonargparse import set_parsing_settings

    set_parsing_settings(docstring_parse_attribute_docstrings=True)


    @dataclass
    class Options:
        """Options for a competition winner."""

        name: str
        """Name of winner."""
        prize: int = 100
        """Amount won."""


.. testcleanup:: docstrings

    set_parsing_settings(docstring_parse_style=DocstringStyle.GOOGLE)
    set_parsing_settings(docstring_parse_attribute_docstrings=False)

Customization of arguments
--------------------------

Since the arguments are added automatically based on the function signatures,
the developer has limited control over their behavior. To customize some of the
arguments, you can create a subclass and override the :meth:`add_argument
<.ActionsContainer.add_argument>` method. For example, by default, ``bool``
arguments require a ``true|false`` value from the command line. To change this
behavior and use :class:`.ActionYesNo` instead, through a CLI based on
:func:`.auto_cli`, you can:

.. testcode::

    from jsonargparse import ArgumentParser, auto_cli

    class CustomArgumentParser(ArgumentParser):
        def add_argument(self, *args, **kwargs):
            if "type" in kwargs and kwargs["type"] == bool:
                kwargs.pop("type")
                kwargs["action"] = ActionYesNo
            return super().add_argument(*args, **kwargs)

    def main_function(flag: bool = False):
        ...

    if __name__ == "__main__":
        auto_cli(main_function, parser_class=CustomArgumentParser)

Classes from functions
----------------------

In some cases there are functions which return an instance of a class. To add
this to a parser such that :meth:`instantiate <.ArgumentParser.instantiate>`
calls this function, the example above would change to:

.. testsetup:: class_from_function

    class MyClass:
        pass


    def instantiate_myclass() -> MyClass:
        return MyClass()

.. testcode:: class_from_function

    from jsonargparse import ArgumentParser
    from jsonargparse.typing import class_from_function

    parser = ArgumentParser()
    dynamic_class = class_from_function(instantiate_myclass)
    parser.add_class_arguments(dynamic_class, "myclass.init")

.. note::

    :func:`.class_from_function` requires the input function to have a return
    type annotation that must be the class type it returns.

Classes created with :func:`.class_from_function` can be selected using
``class_path`` for :ref:`sub-classes`. For example, if
:func:`.class_from_function` is run in a module ``my_module`` as:

.. testcode:: class_from_function

    class_from_function(instantiate_myclass, name="MyClass")

Then the ``class_path`` for the created class would be ``my_module.MyClass``.


Parameter resolvers
-------------------

Three techniques are implemented for resolving signature parameters. One makes
use of Python's `Abstract Syntax Trees (AST)
<https://docs.python.org/3/library/ast.html>`__ library and the second is based
on assumptions of class inheritance. The AST resolver is used first and only
when AST fails, the assumptions resolver is run as fallback. The third resolver
uses stub files ``*.pyi`` and is applied on top of both the AST and assumptions
resolvers.

Unresolved parameters
^^^^^^^^^^^^^^^^^^^^^

The parameter resolvers make a best effort to determine the correct names and
types that the parser should accept. However, there can be cases not yet
supported or cases for which it would be impossible to support. To somewhat
overcome these limitations, there is a special key ``dict_kwargs`` that can be
used to provide arguments that will not be validated during parsing, but will be
used for class instantiation. It is called ``dict_kwargs`` because there are use
cases in which ``**kwargs`` is used just as a dict, thus it also serves that
purpose.

Take for example the following parsing and instantiation:

.. testsetup:: unresolved

    sys.argv = ["", "--myclass=MyClass"]


    class MyClass:
        def __init__(self, foo: int = 0, **kwargs):
            super().__init__(**kwargs)
            ...


    MyClass.__module__ = "jsonargparse_tests"
    jsonargparse_tests.MyClass = MyClass

.. testcode:: unresolved

    from jsonargparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("--myclass", type=MyClass)
    cfg = parser.parse_args()
    cfg_init = parser.instantiate(cfg)

If ``MyClass.__init__`` has ``**kwargs`` with some unresolved parameters, the
following could be a valid config file:

.. code-block:: yaml

    class_path: MyClass
    init_args:
      foo: 1
    dict_kwargs:
      bar: 2

The value for ``bar`` will not be validated, but the class will be instantiated
as ``MyClass(foo=1, bar=2)``.

Assumptions resolver
^^^^^^^^^^^^^^^^^^^^

The assumptions resolver only considers classes. Whenever the ``__init__``
method has ``*args`` and/or ``**kwargs``, the resolver assumes that these are
directly forwarded to the next parent class, i.e. ``__init__`` includes a line
like ``super().__init__(*args, **kwargs)``. Thus, it blindly collects the
``__init__`` parameters of parent classes. The collected parameters will be
incorrect if the code does not follow this pattern. This is why it is only used
as fallback when the AST resolver fails.

.. _ast-resolver:

AST resolver
^^^^^^^^^^^^

The AST resolver analyzes the source code and tries to figure out how the
``*args`` and ``**kwargs`` are used to further find more accepted parameters.
This type of resolving is limited to a few specific cases since there are
endless possibilities for what code can do. The supported cases are illustrated
below. Bear in mind that the code does not need to be exactly like this. The
important detail is how ``*args`` and ``**kwargs`` are used, not other
parameters, or the names of variables, or the complexity of the code that is
unrelated to these variables.

.. testsetup:: ast_resolver

    class BaseClass:
        pass


    class SomeClass:
        def __init__(self, **kwargs):
            pass


    class ChildClass(BaseClass):
        def __init__(self, *args, **kwargs):
            pass

**Cases for statements in functions or methods**

.. testcode:: ast_resolver

    def calls_a_function(*args, **kwargs):
        a_function(*args, **kwargs)


    def calls_a_method(*args, **kwargs):
        an_instance = SomeClass()
        an_instance.a_method(*args, **kwargs)


    def calls_a_static_method(*args, **kwargs):
        an_instance = SomeClass()
        an_instance.a_static_method(*args, **kwargs)


    def calls_a_class_method(*args, **kwargs):
        SomeClass.a_class_method(*args, **kwargs)


    def calls_local_import(**kwargs):
        import some_module
        some_module.a_callable(**kwargs)


    def calls_nested_module_attr(**kwargs):
        import some_module
        some_module.nested.a_callable(**kwargs)


    def pops_from_kwargs(**kwargs):
        val = kwargs.pop("name", "default")


    def gets_from_kwargs(**kwargs):
        val = kwargs.get("name", "default")


    def constant_conditional(**kwargs):
        if global_boolean_1:
            first_function(**kwargs)
        elif not global_boolean_2:
            second_function(**kwargs)
        else:
            third_function(**kwargs)

**Cases for classes**

.. testcode:: ast_resolver

    class PassThrough(BaseClass):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)


    class CallMethod:
        def __init__(self, *args, **kwargs):
            self.a_method(*args, **kwargs)


    class AttributeUseInMethod:
        def __init__(self, **kwargs):
            self._kwargs = kwargs

        def a_method(self):
            a_callable(**self._kwargs)


    class AttributeUseInProperty:
        def __init__(self, **kwargs):
            self._kwargs = kwargs

        @property
        def a_property(self):
            return a_callable(**self._kwargs)


    class DictUpdateUseInMethod:
        def __init__(self, **kwargs):
            self._kwargs = dict(p1=1)  # Can also be: self._kwargs = {'p1': 1}
            self._kwargs.update(**kwargs)  # Can also be: self._kwargs = dict(p1=1, **kwargs)

        def a_method(self):
            a_callable(**self._kwargs)


    class InstanceInClassmethod:
        @classmethod
        def get_instance(cls, **kwargs):
            return cls(**kwargs)


    class NonImmediateSuper(BaseClass):
        def __init__(self, *args, **kwargs):
            super(BaseClass, self).__init__(*args, **kwargs)

**Cases for class instance defaults**

.. testcode:: ast_resolver

    # Class instance: only keyword arguments with ``ast.Constant`` value
    class_instance: SomeClass = SomeClass(param=1)

    # Lambda returning class instance: only keyword arguments with ``ast.Constant`` value
    class_instance: Callable[[type], BaseClass] = lambda a: ChildClass(a, param=2.3)

There can be other parameters apart from ``*args`` and ``**kwargs``, thus in the
cases above, the signatures can be for example like ``name(p1: int, k1: str =
'a', **kws)``. Also when internally calling some function or instantiating a
class, there can be additional parameters. For example in:

.. testcode::

    def calls_a_function(*args, **kwargs):
        a_function(*args, param=1, **kwargs)

The ``param`` parameter would be excluded from the resolved parameters because
it is internally hard coded.

A special case which is supported but with caveats, is multiple calls that use
``**kwargs``. For example:

.. testcode:: ast_resolver

    def conditional_calls(**kwargs):
        if condition_1:
            first_function(**kwargs)
        elif condition_2:
            second_function(**kwargs)
        else:
            third_function(**kwargs)

The resolved parameters that have the same type hint and default across all
calls are supported normally. When there is a discrepancy between the calls, the
parameters behave differently and are shown in the help with the default like
``Conditional<ast-resolver> {DEFAULT_1, ...}``. The main difference is that
these parameters are not included in :meth:`get_defaults
<.ArgumentParser.get_defaults>` or the output of ``--print_config``. This is
necessary because the parser does not know which of the calls will be used at
runtime, and adding them would cause :meth:`instantiate
<.ArgumentParser.instantiate>` to fail due to unexpected keyword arguments.

.. note::

    The parameter resolvers log messages of failures and unsupported cases. To
    view these logs, set the environment variable ``JSONARGPARSE_DEBUG`` to
    ``true``. The supported cases are limited and it is highly encouraged that
    people create issues requesting the support for new ones. However, note
    that when a case is highly convoluted it could be a symptom that the
    respective code is in need of refactoring.

.. _stubs-resolver:

Stubs resolver
^^^^^^^^^^^^^^

The stubs resolver makes use of the `typeshed-client
<https://pypi.org/project/typeshed-client/>`__ package to identify parameters
and their type hints from stub files ``*.pyi``. To enable this resolver, install
jsonargparse with the ``signatures`` extra as explained in section
:ref:`installation`.

Many of the types defined in stub files use the latest syntax for type hints,
that is, bitwise or operator ``|`` for unions, see PEP `604
<https://peps.python.org/pep-0604>`__. This syntax is fully supported.

Most of the types in the Python standard library have their types in stubs. An
example from the standard library would be:

.. doctest:: stubs_resolver

    >>> from random import uniform

    >>> parser = ArgumentParser()
    >>> parser.add_function_arguments(uniform, "uniform")  # doctest: +IGNORE_RESULT
    >>> parser.parse_args(["--uniform.a=0.7", "--uniform.b=3.4"])
    Namespace(uniform=Namespace(a=0.7, b=3.4))

Without the stubs resolver, the :meth:`add_function_arguments
<.ArgumentParser.add_function_arguments>` call requires the
``fail_untyped=False`` option. This has the disadvantage that type ``Any`` is
given to the ``a`` and ``b`` arguments, instead of ``float``. And this means
that the parser would not fail if given an invalid value, for instance a string.

It is not possible to know the defaults of parameters discovered only because of
the stubs. In these cases in the parser help the default is shown as
``Unknown<stubs-resolver>`` and not included in :meth:`get_defaults
<.ArgumentParser.get_defaults>` or the output of ``--print_config``.


.. _dependency-injection:

Dependency injection
====================

Dependency injection is a software design pattern that separates the
instantiation details of objects from their usage, resulting in more loosely
coupled programs, see the `wikipedia article
<https://en.wikipedia.org/wiki/Dependency_injection>`__. Because of its
benefits, support for dependency injection has been a design goal of
jsonargparse.

In Python, dependency injection is achieved by:

- Using as type hint a class, such that the parameter accepts an instance of
  this class or any subclass, e.g. ``module: ModuleBaseClass``.
- Using as type hint a callable that returns an instance of a class, such that
  the parameter accepts a function for instantiation. This could be either
  using ``Callable``, e.g. ``module: Callable[[int], ModuleBaseClass]``, or a
  protocol, e.g. ``module: ModuleFactoryProtocol``.

.. _sub-classes:

Class type and subclasses
-------------------------

When a class is used as a type hint, jsonargparse expects in config files a
dictionary with a ``class_path`` entry indicating the dot notation expression to
import the class, and optionally some ``init_args`` that would be used to
instantiate it. This dictionary is referred to as a **subclass spec**. When
parsing, it will be checked that the class can be imported, that it is a subclass
of the given type and that ``init_args`` values correspond to valid arguments to
instantiate it. After parsing, the config object will include the ``class_path``
and ``init_args`` entries. To get a config object with all nested subclasses
instantiated, the :meth:`instantiate <.ArgumentParser.instantiate>` method is
used.

In addition to using a class as type hint in signatures, for low level
construction of parsers, there are also the methods :meth:`add_class_arguments
<.ArgumentParser.add_class_arguments>` and :meth:`add_subclass_arguments
<.ArgumentParser.add_subclass_arguments>`. These methods accept a ``skip``
argument that can be used to exclude parameters within subclasses. This is done
by giving its relative destination key, i.e. as ``param.init_args.subparam``. An
individual argument can also be added using a class as type, i.e.
``parser.add_argument("--module", type=ModuleBase)``.

A simple example with a top-level class to instantiate, with a parameter that
expects an injected class instance, would use a config file
``config.yaml`` as:

.. code-block:: yaml

    myclass:
      calendar:
        class_path: calendar.Calendar
        init_args:
          firstweekday: 1

Then in Python:

.. testsetup:: subclasses

    cwd = os.getcwd()
    tmpdir = tempfile.mkdtemp(prefix="_jsonargparse_doctest_")
    os.chdir(tmpdir)
    with open("config.yaml", "w") as f:
        f.write("myclass:\n  calendar:\n    class_path: calendar.Calendar\n    init_args:\n      firstweekday: 1\n")

.. testcleanup:: subclasses

    os.chdir(cwd)
    shutil.rmtree(tmpdir)

.. doctest:: subclasses

    >>> from calendar import Calendar

    >>> class MyClass:
    ...     def __init__(self, calendar: Calendar):
    ...         self.calendar = calendar
    ...

    >>> parser = ArgumentParser()
    >>> parser.add_class_arguments(MyClass, "myclass")  # doctest: +IGNORE_RESULT

    >>> cfg = parser.parse_path("config.yaml")
    >>> cfg.myclass.calendar.as_dict()
    {'class_path': 'calendar.Calendar', 'init_args': {'firstweekday': 1}}

    >>> cfg = parser.instantiate(cfg)
    >>> isinstance(cfg.myclass, MyClass)
    True
    >>> isinstance(cfg.myclass.calendar, Calendar)
    True
    >>> cfg.myclass.calendar.getfirstweekday()
    1

In this example the ``class_path`` points to the same class used for the type.
But a subclass of ``Calendar`` with an extended set of init parameters would
also work.

If the previous example were changed to use :meth:`add_subclass_arguments
<.ArgumentParser.add_subclass_arguments>` instead of :meth:`add_class_arguments
<.ArgumentParser.add_class_arguments>`, then subclasses ``MyClass`` would also
be accepted. In this case the config would be like:

.. code-block:: yaml

    myclass:
      class_path: my_module.MyClass
      init_args:
        calendar:
          class_path: calendar.TextCalendar
          init_args:
            firstweekday: 1

.. note::

    Classes will be parsed and instantiated when given as value a dict with
    ``class_path`` and ``init_args`` if the corresponding parameter has type
    ``Any``, or when ``fail_untyped=False`` which defaults to type ``Any``.

    If such a value looks like a subclass spec (has a ``class_path``) but cannot
    be parsed as one, e.g. because the class fails to import, by default it is
    left unchanged and a debug message is logged. Set
    ``validate_subclass_spec_in_any=True`` in :func:`.set_parsing_settings` to
    make the parsing fail in this case instead.

.. note::

    It is also possible to provide to ``class_path`` a function that has as return
    type a class. The accepted ``init_args`` would be the parameters of that
    function.


.. _sub-config-files:

Sub-config files
----------------

Instead of writing a subclass spec inline, a path to a config file that holds it
can be given. This makes it possible to split a large config into smaller
reusable files. It requires that the argument was added with
``sub_configs=True``, which is the default in :func:`.auto_cli` and is accepted
by :meth:`add_argument <.ArgumentParser.add_argument>` and the
``add_*_arguments`` methods.

This also works for the items of a list of classes and for the values of a dict
of classes, which is useful when each component is defined in its own config
file. For example, take the following classes:

.. testcode:: sub_config_files

    class Hook:
        def __init__(self, verbose: bool = False):
            self.verbose = verbose


    class LogHook(Hook):
        def __init__(self, log_file: str = "run.log", **kwargs):
            super().__init__(**kwargs)
            self.log_file = log_file


    class CheckpointHook(Hook):
        def __init__(self, every_n_steps: int = 100, **kwargs):
            super().__init__(**kwargs)
            self.every_n_steps = every_n_steps

.. testcode:: sub_config_files
    :hide:

    doctest_mock_class_in_main(LogHook)
    doctest_mock_class_in_main(CheckpointHook)

And a config in which each hook is a separate file:

.. code-block:: yaml

    # File: hooks.yaml
    hooks:
    - log_hook.yaml
    - checkpoint_hook.yaml

.. code-block:: yaml

    # File: log_hook.yaml
    class_path: LogHook
    init_args:
      log_file: train.log

.. code-block:: yaml

    # File: checkpoint_hook.yaml
    class_path: CheckpointHook
    init_args:
      every_n_steps: 500

.. testsetup:: sub_config_files

    cwd = os.getcwd()
    tmpdir = tempfile.mkdtemp(prefix="_jsonargparse_doctest_")
    os.chdir(tmpdir)
    pathlib.Path("hooks.yaml").write_text("hooks:\n- log_hook.yaml\n- checkpoint_hook.yaml\n")
    pathlib.Path("log_hook.yaml").write_text("class_path: LogHook\ninit_args:\n  log_file: train.log\n")
    pathlib.Path("checkpoint_hook.yaml").write_text("class_path: CheckpointHook\ninit_args:\n  every_n_steps: 500\n")

.. testcleanup:: sub_config_files

    os.chdir(cwd)
    shutil.rmtree(tmpdir)

Then in Python:

.. doctest:: sub_config_files

    >>> parser = ArgumentParser()
    >>> parser.add_argument("--hooks", type=list[Hook], sub_configs=True)  # doctest: +IGNORE_RESULT

    >>> cfg = parser.parse_path("hooks.yaml")
    >>> cfg.hooks[0].class_path
    '__main__.LogHook'
    >>> cfg.hooks[0].init_args.log_file
    'train.log'
    >>> cfg.hooks[1].init_args.every_n_steps
    500

    >>> init = parser.instantiate(cfg)
    >>> isinstance(init.hooks[1], CheckpointHook)
    True

The same is accepted from command line, i.e. ``--hooks=[log_hook.yaml,
checkpoint_hook.yaml]``, or appending one item at a time as explained in
:ref:`list-append`, i.e. ``--hooks+=log_hook.yaml
--hooks+=checkpoint_hook.yaml``.

Relative paths inside a sub-config file are resolved with respect to the
directory of that sub-config file, such that a group of config files can be
moved around without needing to modify them. Furthermore, :meth:`save
<.ArgumentParser.save>` with ``multifile=True`` writes back each sub-config to
its own file, preserving the original structure.


.. _instance-factories:

Instance factories
------------------

As explained at the beginning of section :ref:`dependency-injection`, callables
that return instances of classes, referred to as instance factories, represent
an alternative approach to dependency injection. This is useful to support
dependency injection of classes that require parameters that are only available
after injection. For this case, when :meth:`instantiate
<.ArgumentParser.instantiate>` is run, a partial function is provided, which
might accept parameters and return the instance of the class. Two options are
possible: using ``Callable`` or ``Protocol``. To illustrate the ``Callable``
option, take for example the classes:

.. testcode:: callable

    class Optimizer:
        def __init__(self, params: Iterable):
            self.params = params


    class SGD(Optimizer):
        def __init__(self, params: Iterable, lr: float):
            super().__init__(params)
            self.lr = lr

.. testcode:: callable
    :hide:

    doctest_mock_class_in_main(SGD)

A possible parser and callable behavior would be:

.. doctest:: callable

    >>> value = {
    ...     "class_path": "SGD",
    ...     "init_args": {
    ...         "lr": 0.01,
    ...     },
    ... }

    >>> parser.add_argument("--optimizer", type=Callable[[Iterable], Optimizer])  # doctest: +IGNORE_RESULT
    >>> cfg = parser.parse_args(["--optimizer", str(value)])
    >>> cfg.optimizer
    Namespace(class_path='__main__.SGD', init_args=Namespace(lr=0.01))
    >>> init = parser.instantiate(cfg)
    >>> optimizer = init.optimizer([1, 2, 3])
    >>> isinstance(optimizer, SGD)
    True
    >>> optimizer.params, optimizer.lr
    ([1, 2, 3], 0.01)

.. note::

    When the ``Callable`` has a class return type, it is possible to specify the
    ``class_path`` giving only its name if imported before parsing, as explained
    in :ref:`sub-classes-command-line`.

If the same type above is used as type hint of a parameter of another class, a
default can be set using a lambda, for example:

.. testcode:: callable

    class Model:
        def __init__(
            self,
            optimizer: Callable[[Iterable], Optimizer] = lambda p: SGD(p, lr=0.05),
        ):
            self.optimizer = optimizer

Then a parser and behavior could be:

.. code-block::

    >>> parser.add_class_arguments(Model, 'model')
    >>> cfg = parser.get_defaults()
    >>> cfg.model.optimizer
    Namespace(class_path='__main__.SGD', init_args=Namespace(lr=0.05))
    >>> init = parser.instantiate(cfg)
    >>> optimizer = init.model.optimizer([1, 2, 3])
    >>> optimizer.params, optimizer.lr
    ([1, 2, 3], 0.05)

See :ref:`ast-resolver` for limitations of lambda defaults in signatures.
Providing a lambda default to :meth:`add_argument
<.ActionsContainer.add_argument>` does not work since there is no AST resolving.
In this case, a dict with ``class_path`` and ``init_args`` can be used as
default.

Multiple arguments required after injection is also supported and can be
specified the same way with a ``Callable``. For example, for two
``Iterable`` arguments, you can use the syntax: ``Callable[[Iterable,
Iterable], Type]``. Similarly, for a callable that accepts zero
arguments, the syntax would be ``Callable[[], Type]``.

Note the big limitation that ``Callable`` has. It is only possible to specify
positional and unnamed parameters. To overcome this limitation, the second
option, a callable ``Protocol`` can be used instead. Building up from the same
example, an ``OptimizerFactory`` protocol can be defined as:

.. testcode:: callable

    class OptimizerFactory(Protocol):
        def __call__(self, params: Iterable) -> Optimizer: ...

Then a parser and protocol behavior would be:

.. testcode:: callable
    :hide:

    parser = ArgumentParser()

.. doctest:: callable

    >>> value = {
    ...     "class_path": "SGD",
    ...     "init_args": {
    ...         "lr": 0.02,
    ...     },
    ... }

    >>> parser.add_argument("--optimizer", type=OptimizerFactory)  # doctest: +IGNORE_RESULT
    >>> cfg = parser.parse_args(["--optimizer", str(value)])
    >>> cfg.optimizer
    Namespace(class_path='__main__.SGD', init_args=Namespace(lr=0.02))
    >>> init = parser.instantiate(cfg)
    >>> optimizer = init.optimizer(params=[6, 5])
    >>> optimizer.params, optimizer.lr
    ([6, 5], 0.02)

The key difference with respect to the ``Callable`` is being able to call
``init.optimizer()`` with keyword arguments ``params=[6, 5]``.

.. _sub-classes-command-line:

Command line
------------

The help of the parser does not show accepted parameters of a class since this
depends on the chosen subclass. To get details for a particular subclass there
is a help option that receives the import path. Take for example a parser
defined as:

.. testcode::

    from calendar import Calendar
    from jsonargparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("--calendar", type=Calendar)

The help for a corresponding subclass could be printed as:

.. code-block:: bash

    python tool.py --calendar.help calendar.TextCalendar

In the command line, a subclass can be specified through multiple command line
arguments:

.. code-block:: bash

    python tool.py \
      --calendar.class_path calendar.TextCalendar \
      --calendar.init_args.firstweekday 1

For convenience, the arguments can be somewhat shorter by omitting
``.class_path`` and ``.init_args`` and only specifying the name of the subclass
instead of the full import path.

.. code-block:: bash

    python tool.py --calendar TextCalendar --calendar.firstweekday 1

Specifying the name of the subclass works for subclasses in modules that have
been imported before parsing. Abstract classes and private classes (module or
name starting with ``'_'``) are not considered. All the subclasses resolvable by
its name can be seen in the general help ``python tool.py --help``.

When the base class is not abstract, the ``class_path`` can be omitted, by
giving directly ``init_args``, for example:

.. code-block:: bash

    python tool.py --calendar.firstweekday 2

would implicitly use ``calendar.Calendar`` as the class path.


Default values
--------------

For a parameter that has a class as type, it might also be wanted to set a
default value for it. Special care must be taken when doing this, could be
considered bad practice and be a good idea to avoid in most cases. The issue is
that classes are normally mutable. Depending on how the parameter value is used,
its default class instance in the signature could be changed. This goes against
what a default value is expected to be and lead to bugs which are difficult to
debug.

Since there are some legitimate use cases for class instances in defaults, they
are supported with a particular behavior and recommendations. An example is:

.. testcode:: instance_default

    class MyClass:
        def __init__(
            self,
            calendar: Calendar = Calendar(firstweekday=1),
        ):
            self.calendar = calendar

Adding this class to a parser will work without issues. The :ref:`ast-resolver`
in limited cases determines how to instantiate the original default. The parsing
methods would provide a dict with ``class_path`` and ``init_args`` instead of
the class instance. Furthermore, if :meth:`instantiate
<.ArgumentParser.instantiate>` is used, a new instance of the class is created,
thereby avoiding issues related to the mutability of the default.

Since the :ref:`ast-resolver` only supports limited cases, or when the source
code is not available, a second approach is to use the special function
:func:`.lazy_instance` to instantiate the default. Continuing with the same
example above, this would be:

.. testcode:: instance_default

    from jsonargparse.typing import lazy_instance


    class MyClass:
        def __init__(
            self,
            calendar: Calendar = lazy_instance(Calendar, firstweekday=1),
        ):
            self.calendar = calendar

Like this, the parsed default will be a dict with ``class_path`` and
``init_args``, again avoiding the risk of mutability.

The use of :func:`.lazy_instance` is somewhat discouraged. A function that
delays the initialization of instances, and works for all possible cases out
there, is challenging. The current implementation is known to have some
problems. Instead of using :func:`.lazy_instance`, you could consider switching
to :ref:`instance-factories`.

.. note::

    In Python there can be some classes or functions for which it is not
    possible to determine its import path from the object alone. When using one
    of these as a default would cause a failure when serializing because what
    gets saved in the config file is the import path. To overcome this problem
    use the :func:`.register_unresolvable_import_paths` function giving it the
    module from where the respective object can be imported.


.. _subclasses-disabled:

Class types with subclasses disabled
------------------------------------

In certain situations, it is preferable to use a class as a type hint with no
intention to receive subclasses. From a parser perspective, this means that
providing a subclass is not permitted, and when serializing, the instantiation
arguments are stored directly, without including ``class_path`` and
``init_args``. The standard Python approach for this scenario is to decorate
classes with :func:`.final`, which explicitly indicates that subclassing is not
intended. A parsing example would be:

.. testcode:: final_classes

    from jsonargparse.typing import final


    @final
    class FinalClass:
        def __init__(self, number: int = 0, accepted: bool = False):
            ...


    parser = ArgumentParser()
    parser.add_argument("--data", type=FinalClass)
    cfg = parser.parse_args(["--data.number=8", "--data.accepted=true"])

for which a dump would give as output:

.. doctest:: final_classes

    >>> print(parser.dump(cfg))  # doctest: +NORMALIZE_WHITESPACE
    data:
      number: 8
      accepted: true

In some cases, subclasses are not intended, but the :func:`.final` decorator is
not applied. For example, having ``class_path`` for a simple ``x, y``
coordinates dataclass would be unnecessarily cumbersome. For this reason,
``jsonargparse`` early on, implemented the same behavior for pure (not mixed
with normal classes) ``dataclasses``, attrs' ``define``, pydantic's
``dataclass``, and pydantic's ``BaseModel`` classes.  However, since these
classes technically support subclassing, subclass support can be enabled as
described below. Subclass support has been kept disabled for these types by
default to avoid introducing breaking changes.


.. _enable-disable-subclasses:

Enable/disable subclasses
-------------------------

The :func:`.set_parsing_settings` function provides the ``subclasses_disabled``
and ``subclasses_enabled`` parameters, which, as their names suggest, control
which class types support subclasses. The ``subclasses_disabled`` parameter
accepts a list of class types and functions. When a type is provided, that type
and its descendants will have subclass support disabled. Functions in the list
should accept a type and return ``True`` if subclasses should be disabled for
that type.

The ``subclasses_enabled`` parameter accepts a list of class types and function
names. When a type is provided, both the type and its descendants will have
subclass support enabled. Types specified in ``subclasses_enabled`` take
precedence over those in ``subclasses_disabled``. If a function name is given to
``subclasses_enabled``, it must correspond to a function previously registered
in ``subclasses_disabled``; in this case, the effect is to unregister it. By
default, the following disabling functions are registered: ``is_pure_dataclass``,
``is_pydantic_model``, ``is_attrs_class``, and ``is_final_class``.

Some examples. Since ``subclasses_enabled`` takes precedence, it is possible to
keep subclass support disabled for dataclasses, but enable it for a specific
dataclass as follows:

.. testsetup:: enable_disable_subclasses

    selectors = _common.subclasses_disabled_selectors
    _common.subclasses_disabled_selectors = selectors.copy()

    @dataclass
    class DataClassBaseType:
        pass

.. testcleanup:: enable_disable_subclasses

    _common.subclasses_disabled_selectors = selectors

.. testcode:: enable_disable_subclasses

    from jsonargparse import set_parsing_settings

    set_parsing_settings(subclasses_enabled=[DataClassBaseType])

To enable subclass support for all pydantic models, the following can be done:

.. testcode:: enable_disable_subclasses

    set_parsing_settings(subclasses_enabled=["is_pydantic_model"])

To enable subclass support for all dataclasses, but have it disabled for a
specific dataclass, the following can be done:

.. testcode:: enable_disable_subclasses

    set_parsing_settings(
        subclasses_enabled=["is_pure_dataclass"],
        subclasses_disabled=[DataClassBaseType],
    )

.. note::

    Enabling subclass support for types is currently experimental. While the
    interface and behavior is expected to be stable, fundamental issues may
    arise that require changes to the design, which could result in breaking
    changes in future releases.


.. _argument-linking:

Argument linking
================

Some use cases could require adding arguments from multiple classes and some
parameters get a value automatically computed from other arguments. This
behavior can be obtained by using the :meth:`link_arguments
<.ArgumentParser.link_arguments>` parser method.

There are two types of links, defined with ``apply_on='parse'`` or
``apply_on='instantiate'``. As the names suggest, the former are set when
calling one of the parse methods and the latter are set when calling
:meth:`instantiate <.ArgumentParser.instantiate>`.

Applied on parse
----------------

For parsing links, source keys can be individual arguments or nested groups. The
target key has to be a single argument. The keys can be inside ``init_args`` of
a subclass. The compute function should accept as many positional arguments as
there are sources and return a value of type compatible with the target. An
example would be the following:

.. testcode::

    class Model:
        def __init__(self, batch_size: int):
            self.batch_size = batch_size


    class Data:
        def __init__(self, batch_size: int = 5):
            self.batch_size = batch_size


    parser = ArgumentParser()
    parser.add_class_arguments(Model, "model")
    parser.add_class_arguments(Data, "data")
    parser.link_arguments("data.batch_size", "model.batch_size", apply_on="parse")

As argument and in config files only ``data.batch_size`` should be specified.
Then whatever value it has will be propagated to ``model.batch_size``.

An example of a target being in a subclass is:

.. testcode::

    class Logger:
        def __init__(self, save_dir: str | None = None):
            self.save_dir = save_dir

    class Trainer:
        def __init__(
            self,
            save_dir: str | None = None,
            logger: bool | Logger | list[Logger] = False,
        ):
            self.logger = logger

    parser = ArgumentParser()
    parser.add_class_arguments(Trainer, "trainer")
    parser.link_arguments("trainer.save_dir", "trainer.logger.init_args.save_dir")

The link gets applied to the ``logger`` parameter when it is a single subclass
and applied to all elements of a list of subclasses. If a subclass does not
define the targeted ``init_args`` parameter, the link is ignored.

Applied on instantiate
----------------------

For instantiation links, sources can be class groups (added with
:meth:`add_class_arguments <.ArgumentParser.add_class_arguments>`) or subclass
arguments (see :ref:`sub-classes`). The source key can be the entire
instantiated object or an attribute of the object. The target key has to be a
single argument and can be inside init_args of a subclass. The order of
instantiation used by :meth:`instantiate <.ArgumentParser.instantiate>` is
automatically determined based on the links. The set of all instantiation links
must be a directed acyclic graph. An example would be the following:

.. testcode::

    class Model:
        def __init__(self, num_classes: int):
            self.num_classes = num_classes


    class Data:
        def __init__(self):
            self.num_classes = get_num_classes()


    parser = ArgumentParser()
    parser.add_class_arguments(Model, "model")
    parser.add_class_arguments(Data, "data")
    parser.link_arguments("data.num_classes", "model.num_classes", apply_on="instantiate")

This link would imply that :meth:`instantiate <.ArgumentParser.instantiate>`
instantiates ``Data`` first, then use the ``num_classes`` attribute to
instantiate ``Model``.


OmegaConf variable interpolation
================================

One of the possible reasons to add a parser mode (see :ref:`custom-loaders`) can
be to have support for variable interpolation in YAML files. Any library could
be used to implement a loader and configure a mode for it. Without needing to
implement a loader function, an ``omegaconf`` parser mode is available out of
the box when this package is installed.

Take for example a YAML file as:

.. code-block:: yaml

    server:
      host: localhost
      port: 80
    client:
      url: http://${server.host}:${server.port}/

.. testsetup:: omegaconf

    example = """
    server:
      host: localhost
      port: 80
    client:
      url: http://${server.host}:${server.port}/
    """
    cwd = os.getcwd()
    tmpdir = tempfile.mkdtemp(prefix="_jsonargparse_doctest_")
    os.chdir(tmpdir)
    with open("example.yaml", "w") as f:
        f.write(example)

.. testcleanup:: omegaconf

    os.chdir(cwd)
    shutil.rmtree(tmpdir)

This YAML could be parsed as follows:

.. doctest:: omegaconf

    >>> @dataclass
    ... class ServerOptions:
    ...     host: str
    ...     port: int
    ...

    >>> @dataclass
    ... class ClientOptions:
    ...     url: str
    ...

    >>> parser = ArgumentParser(parser_mode="omegaconf")
    >>> parser.add_argument("--server", type=ServerOptions)  # doctest: +IGNORE_RESULT
    >>> parser.add_argument("--client", type=ClientOptions)  # doctest: +IGNORE_RESULT
    >>> parser.add_argument("--config", action="config")  # doctest: +IGNORE_RESULT

    >>> cfg = parser.parse_args(["--config=example.yaml"])
    >>> cfg.client.url
    'http://localhost:80/'

.. note::

    The ``parser_mode="omegaconf"`` provides support for `OmegaConf's resolvers
    <https://omegaconf.readthedocs.io/en/latest/usage.html#variable-interpolation>`__
    in a single YAML file. It is not possible to do interpolation across
    multiple YAML files or in an isolated individual command line argument.

Experimental ``omegaconf+`` mode
--------------------------------

An experimental ``omegaconf+`` parser mode is available, which addresses the
limitations of the ``omegaconf`` mode mentioned earlier. Instead of applying
OmegaConf resolvers to each YAML config individually, the resolving is performed
once at the end of the parsing process. As a result, in nested subconfigs,
references to nodes must be either relative or parser-level absolute to function
correctly. Alternatively, you can
``set_parsing_settings(omegaconf_absolute_to_relative_paths=True)`` to enable
automatic conversion of absolute paths to relative ones during parsing. Be aware
that this automatic conversion does not work for every possible case.

Based on community feedback, this mode may become the default ``omegaconf`` mode
in version 5.0.0. This change would introduce a breaking modification, as
absolute node references would no longer work in nested subconfigs.


.. _environment-variables:

Environment variables
=====================

jsonargparse parsers can also get values from environment variables. The
parser checks existing environment variables whose name is of the form
``[PREFIX_][LEV__]*OPT``, that is, all in upper case, first a prefix (set by
``env_prefix``, or if unset the ``prog`` without extension or none if set to False)
followed by underscore and then the argument name replacing dots with two underscores.
Using the parser from the :ref:`nested-namespaces` section above, in your shell you
would set the environment variables as:

.. code-block:: bash

    export APP_LEV1__OPT1='from env 1'
    export APP_LEV1__OPT2='from env 2'

Then in Python the parser would use these variables, unless overridden by the
command line arguments, that is:

.. testsetup:: env

    os.environ["APP_LEV1__OPT1"] = "from env 1"
    os.environ["APP_LEV1__OPT2"] = "from env 2"

.. doctest:: env

    >>> parser = ArgumentParser(env_prefix="APP", default_env=True)
    >>> parser.add_argument("--lev1.opt1", default="from default 1")  # doctest: +IGNORE_RESULT
    >>> parser.add_argument("--lev1.opt2", default="from default 2")  # doctest: +IGNORE_RESULT
    >>> cfg = parser.parse_args(["--lev1.opt1", "from arg 1"])
    >>> cfg.lev1.opt1
    'from arg 1'
    >>> cfg.lev1.opt2
    'from env 2'

Note that when creating the parser, ``default_env=True`` was given. By default
:meth:`parse_args <.ArgumentParser.parse_args>` does not parse environment
variables. If ``default_env`` is left unset, environment variable parsing can
also be enabled by setting in your shell ``JSONARGPARSE_DEFAULT_ENV=true``.

There is also the :meth:`parse_env <.ArgumentParser.parse_env>` function to only
parse environment variables, which might be useful for some use cases in which
there is no command line call involved.

If a parser includes an ``action="config"`` argument, then the environment
variable for this config file will be parsed before all the other environment
variables.


.. _sub-commands:

Subcommands
===========

Subcommands provide a modular approach to defining parsers, similar to the
concept of `subcommands
<https://docs.python.org/3/library/argparse.html#subcommands>`__ in argparse.
However, in jsonargparse, subcommands behave somewhat differently; refer to
:ref:`argparse-deviations` for further details.

To incorporate subcommands into a parser, use the :meth:`add_subcommands
<.ArgumentParser.add_subcommands>` method. You can then add an existing parser
as a subcommand via :meth:`add_subcommand <.ActionSubCommands.add_subcommand>`.
In the resulting parsed namespace, the selected subcommand is stored under the
``subcommand`` key (or the key specified by ``dest``), and the arguments for the
subcommand are nested under a key matching the subcommand's name. The following
example demonstrates how to define a parser with subcommands:

.. testcode::

    from jsonargparse import ArgumentParser

    ...
    parser_subcomm1 = ArgumentParser()
    parser_subcomm1.add_argument("--op1")
    ...
    parser_subcomm2 = ArgumentParser()
    parser_subcomm2.add_argument("--op2")
    ...
    parser = ArgumentParser(prog="app")
    parser.add_argument("--op0")
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("subcomm1", parser_subcomm1)
    subcommands.add_subcommand("subcomm2", parser_subcomm2)

Then some examples of parsing are the following:

.. doctest::

    >>> parser.parse_args(["subcomm1", "--op1", "val1"])  # doctest: +IGNORE_RESULT
    Namespace(op0=None, subcommand='subcomm1', subcomm1=Namespace(op1='val1'))
    >>> parser.parse_args(["--op0", "val0", "subcomm2", "--op2", "val2"])  # doctest: +IGNORE_RESULT
    Namespace(op0='val0', subcommand='subcomm2', subcomm2=Namespace(op2='val2'))

Parsing config files with :meth:`parse_path <.ArgumentParser.parse_path>` or
:meth:`parse_string <.ArgumentParser.parse_string>` is also possible. The config
file is not required to specify a value for ``subcommand``. For the example
parser above a valid YAML would be:

.. code-block:: yaml

    # File: example.yaml
    op0: val0
    subcomm1:
      op1: val1

Parsing of environment variables works similar to :class:`.ActionParser`. For
the example parser above, all environment variables for ``subcomm1`` would have
as prefix ``APP_SUBCOMM1_`` and likewise for ``subcomm2`` as prefix
``APP_SUBCOMM2_``. The subcommand to use could be chosen by setting environment
variable ``APP_SUBCOMMAND``.

It is possible to have multiple levels of subcommands. With multiple levels
there is one basic requirement: the subcommands must be added in the order of
the levels. That is, first call :meth:`add_subcommands
<.ArgumentParser.add_subcommands>` and :meth:`add_subcommand
<.ActionSubCommands.add_subcommand>` for the first level. Only after do the
same for the second level, and so on.


.. _json-schemas:

JSON Schemas
============

The :class:`.ActionJsonSchema` class is provided to allow parsing and validation
of values using a JSON Schema. This class requires the `jsonschema
<https://pypi.org/project/jsonschema/>`__ Python package. Though note that
``jsonschema`` is not a requirement of the minimal jsonargparse install. To
enable this functionality install with the ``jsonschema`` extra as explained in
section :ref:`installation`.

Check out the `JSON Schema documentation
<https://python-jsonschema.readthedocs.io/>`__ to learn how to write a schema.
The current version of jsonargparse uses Draft7Validator. Parsing an argument
using a JSON Schema is done like in the following example:

.. doctest::

    >>> from jsonargparse import ActionJsonSchema

    >>> schema = {
    ...     "type": "object",
    ...     "properties": {
    ...         "price": {"type": "number"},
    ...         "name": {"type": "string"},
    ...     },
    ... }

    >>> parser = ArgumentParser()
    >>> parser.add_argument("--json", action=ActionJsonSchema(schema=schema))  # doctest: +IGNORE_RESULT

    >>> parser.parse_args(["--json", '{"price": 1.5, "name": "cookie"}'])
    Namespace(json={'price': 1.5, 'name': 'cookie'})

Instead of giving a JSON string as argument value, it is also possible to
provide a path to a JSON/YAML file, which would be loaded and validated against
the schema. If the schema defines default values, these will be used by the
parser to initialize the config values that are not specified. When adding an
argument with the :class:`.ActionJsonSchema` action, you can use "%s" in the
``help`` string so that in that position the schema is printed.


.. _jsonnet-files:

Jsonnet files
=============

The Jsonnet support requires `jsonschema
<https://pypi.org/project/jsonschema/>`__ and `jsonnet
<https://pypi.org/project/jsonnet/>`__ Python packages which are not included
with minimal jsonargparse install. To enable this functionality install
jsonargparse with the ``jsonnet`` extra as explained in section
:ref:`installation`.

By default an :class:`.ArgumentParser` parses config files as YAML. However, if
instantiated giving ``parser_mode='jsonnet'``, then :meth:`parse_args
<.ArgumentParser.parse_args>`, :meth:`parse_path <.ArgumentParser.parse_path>`
and :meth:`parse_string <.ArgumentParser.parse_string>` will expect config files
to be in Jsonnet format instead. Example:

.. testsetup:: jsonnet

    cwd = os.getcwd()
    tmpdir = tempfile.mkdtemp(prefix="_jsonargparse_doctest_")
    os.chdir(tmpdir)
    with open("example.jsonnet", "w") as f:
        f.write("{}\n")

.. testcleanup:: jsonnet

    os.chdir(cwd)
    shutil.rmtree(tmpdir)

.. testcode:: jsonnet

    from jsonargparse import ArgumentParser

    parser = ArgumentParser(parser_mode="jsonnet")
    parser.add_argument("--config", action="config")
    cfg = parser.parse_args(["--config", "example.jsonnet"])

Jsonnet files are commonly parametrized, thus requiring external variables for
parsing. For these cases, instead of changing the parser mode away from
``yaml``, the :class:`.ActionJsonnet` class can be used. This action allows to
define an argument which would be a Jsonnet string or a path to a Jsonnet file.
Moreover, another argument can be specified as the source for any external
variables required, which would be either a path to or a string containing a
JSON dictionary of variables. Its use would be as follows:

.. testcode:: jsonnet

    from jsonargparse import ArgumentParser, ActionJsonnet

    parser = ArgumentParser()
    parser.add_argument("--in_ext_vars", type=dict)
    parser.add_argument("--in_jsonnet", action=ActionJsonnet(ext_vars="in_ext_vars"))

For example, if a Jsonnet file required some external variable ``param``, then
the Jsonnet and the external variable could be given as:

.. testcode:: jsonnet

    cfg = parser.parse_args(["--in_ext_vars", '{"param": 123}', "--in_jsonnet", "example.jsonnet"])

Note that the external variables argument must be provided before the Jsonnet
path so that this dictionary already exists when parsing the Jsonnet.

The :class:`.ActionJsonnet` class also accepts as argument a JSON Schema, in
which case the Jsonnet would be validated against this schema right after
parsing.


.. _parser-arguments:

Parsers as arguments
====================

Sometimes it is useful to take an already existing parser that is required
standalone in some part of the code, and reuse it to parse an inner node of
another more complex parser. For these cases an argument can be defined using
the :class:`.ActionParser` class. An example of how to use this class is the
following:

.. testcode::

    from jsonargparse import ArgumentParser, ActionParser

    inner_parser = ArgumentParser(prog="app1")
    inner_parser.add_argument("--op1")
    ...
    outer_parser = ArgumentParser(prog="app2")
    outer_parser.add_argument("--inner.node", title="Inner node title", action=ActionParser(parser=inner_parser))

When using the :class:`.ActionParser` class, the value of the node in a config
file can be either the complex node itself, or the path to a file which will be
loaded and parsed with the corresponding inner parser. Naturally using
``action="config"`` to parse a complete config file will parse the inner
nodes correctly.

Note that when adding ``inner_parser`` a title was given. In the help, the added
parsers are shown as independent groups starting with the given ``title``. It is
also possible to provide a ``description``.

Regarding environment variables, the prefix of the outer parser will be used to
populate the leaf nodes of the inner parser. In the example above, if
``inner_parser`` is used to parse environment variables, then as normal
``APP1_OP1`` would be checked to populate option ``op1``. But if
``outer_parser`` is used, then ``APP2_INNER__NODE__OP1`` would be checked to
populate ``inner.node.op1``.

An important detail to note is that the parsers that are given to
:class:`.ActionParser` are internally modified. Therefore, to use the parser
both as standalone and as inner node, it is necessary to implement a function
that instantiates the parser. This function would be used in one place to get an
instance of the parser for standalone parsing, and in some other place use the
function to provide an instance of the parser to :class:`.ActionParser`.


.. _tab-completion:

Tab completion
==============

Tab completion is available for jsonargparse parsers by using either the `shtab
<https://pypi.org/project/shtab/>`__ package or the `argcomplete
<https://pypi.org/project/argcomplete/>`__ package.

shtab
-----

For ``shtab`` to work, there is no need to set ``complete``/``choices`` to the
parser actions, and no need to call `shtab.add_argument_to
<https://docs.iterative.ai/shtab/ref/#add_argument_to>`__. This is done
automatically by :meth:`parse_args <.ArgumentParser.parse_args>`. The only
requirement is to install shtab either directly or by installing jsonargparse
with the ``shtab`` extra as explained in section :ref:`installation`.

There are two ways to generate shell completion scripts when ``shtab`` is
installed: via the :meth:`.ArgumentParser.get_completion_script` method or by
enabling a command-line argument.

Programmatic generation
^^^^^^^^^^^^^^^^^^^^^^^

The :meth:`.ArgumentParser.get_completion_script` method can be used to
generate completion scripts programmatically. The method accepts a
``completion_type`` parameter that specifies the shell. For shtab, use
``shtab-`` followed by the shell name (e.g., ``shtab-bash``, ``shtab-zsh``).

.. testcode::

    from jsonargparse import ArgumentParser

    parser = ArgumentParser(prog="example")
    parser.add_argument("--bool", type=bool)

    script = parser.get_completion_script("shtab-bash", preambles=[])
    # script now contains the bash completion script

.. warning::

    After calling :meth:`.get_completion_script`, the parser instance is
    invalidated and cannot be used for parsing arguments. Create a new parser
    instance if you need to parse arguments afterward.

Command-line argument
^^^^^^^^^^^^^^^^^^^^^

To enable generation of completion scripts via a command-line argument, use
:func:`.set_parsing_settings` with ``add_print_completion_argument=True``. This
adds a ``--print_completion`` argument to top-level parsers (not subparsers).

.. testcode::

    from jsonargparse import set_parsing_settings

    set_parsing_settings(add_print_completion_argument=True)

With this setting enabled, completion scripts can be generated from the command
line. For example, in Linux to enable bash completions for all users, as root:

.. code-block:: bash

    # example.py --print_completion=shtab-bash > /etc/bash_completion.d/example

Without installing, completion scripts can be tested by sourcing or evaluating
them:

.. code-block:: bash

    $ eval "$(example.py --print_completion=shtab-bash)"

Without changing python code, it is also possible to add the ``--print_completion``
argument by setting the environment variable
``JSONARGPARSE_ADD_PRINT_COMPLETION_ARGUMENT=true``.

Completion behavior
^^^^^^^^^^^^^^^^^^^

The scripts work both to complete when there are choices, but also gives
instructions to the user for guidance. Take for example the parser:

.. testsetup:: tab_completion

    sys.argv = [""]

.. testcode:: tab_completion

    #!/usr/bin/env python3

    from jsonargparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("--bool", type=bool | None)

    parser.parse_args()

The completions print the type of the argument, how many options are matched,
and afterward the list of choices matched up to that point. If only one option
matches, then the value is completed without printing guidance. For example:

.. code-block:: bash

    $ example.py --bool <TAB><TAB>
    Expected type: bool | None; 3/3 matched choices
    true  false  null
    $ example.py --bool f<TAB>
    $ example.py --bool false

For the case of subclass types, the import class paths for known subclasses are
completed, both for the switch to select the class and for the corresponding
``--*.help`` switch. The ``init_args`` for known subclasses are also completed,
giving as guidance which of the subclasses accepts it. An example would be:

.. code-block:: bash

    $ example.py --cls <TAB><TAB>
    Expected type: BaseClass; 3/3 matched choices
    some.module.BaseClass     other.module.SubclassA
    other.module.SubclassB
    $ example.py --cls other.module.SubclassA --cls.<TAB><TAB>
    --cls.param1    --cls.param2
    $ example.py --cls other.module.SubclassA --cls.param2 <TAB><TAB>
    Expected type: int; Accepted by subclasses: SubclassA

argcomplete
-----------

For ``argcomplete`` to work, there is no need to implement completer functions
or to call `argcomplete.autocomplete
<https://kislyuk.github.io/argcomplete/#argcomplete.autocomplete>`__ since this
is done automatically by :meth:`parse_args <.ArgumentParser.parse_args>`. The
only requirement to enable tab completion is to install argcomplete either
directly or by installing jsonargparse with the ``argcomplete`` extra as
explained in section :ref:`installation`.

The tab completion can be enabled `globally
<https://kislyuk.github.io/argcomplete/#global-completion>`__ for all
argcomplete compatible tools or for each `individual
<https://kislyuk.github.io/argcomplete/#synopsis>`__ tool.

Using the same ``bool`` example as shown above, activate tab completion and use
it as follows:

.. code-block:: bash

    $ eval "$(register-python-argcomplete example.py)"

    $ example.py --bool <TAB><TAB>
    false  null   true
    $ example.py --bool f<TAB>
    $ example.py --bool false


.. _argparse-deviations:

Deviations from argparse
========================

To ensure a high level of compatibility with argparse, the argparse tests from
the Python standard library are run against jsonargparse. Some of these tests
are skipped for the following reasons: 1) they cover intentional deviations from
argparse, 2) they are not relevant for jsonargparse, or 3) they are under
investigation and may be enabled in the future. The tests to skip are configured
in the ``argparse_tests_generate.py`` file.

The following sections describe the main intentional deviations from argparse.
In addition, deprecated features in argparse are not supported.

Subcommands
-----------

In argparse, when a parser has subcommands, the resulting namespace merges the
main parser and subparser options into a single flat namespace. Since
jsonargparse supports nested namespaces, it was a deliberate design choice to
place subcommand options in a dedicated subnamespace for greater clarity and
user convenience.

Additionally, in argparse, ``add_subparsers`` must be called with the ``dest``
parameter to include the name of the selected subcommand in the resulting
namespace. In jsonargparse, the chosen subcommand is available by default,
without requiring any extra parameters.

Furthermore, to promote modularity, subparsers in jsonargparse can be created
independently, just like the main parser. The subparser object is then added as
a subcommand. This enables defining functions that return subparsers, which can
be used both as standalone parsers and as subcommands. In contrast, argparse
subparsers are tightly coupled to the main parser and cannot be defined
independently. To avoid confusion with respect to argparse, the method names for
adding subcommands in jsonargparse are intentionally different.

To migrate from argparse to jsonargparse, instead of:

.. testcode::

    import argparse

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    subparser1 = subparsers.add_parser("foo")
    subparser1.add_argument("--key")
    ...

The code would be changed to:

.. testcode::

    import jsonargparse

    subparser1 = jsonargparse.ArgumentParser()
    subparser1.add_argument("--key")

    ...

    parser = jsonargparse.ArgumentParser()
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("foo", subparser1)

Parse known arguments
---------------------

Argparse provides the ``parse_known_args`` method, which allows for more lenient
parsing by ignoring unrecognized arguments. However, jsonargparse is designed
for complex parsing scenarios, such as: multiple subcommands, a large number of
arguments derived from signatures, class instantiation, and configuration files.
Allowing unrecognized arguments could make it harder for users to detect errors,
such as typos in configuration files. For this reason, jsonargparse
intentionally does not support ``parse_known_args``.

User defined types
------------------

In argparse, when adding an argument, the ``type`` parameter can be set to a
user-defined function or class. Providing a function is supported in
jsonargparse, with the additional requirement that the function must be
idempotent. That is, applying the function two or more times should not alter
the value. For example:

.. testcode::

    # either int larger than zero or 'off' string
    def int_or_off(x):
        return x if x == "off" else int(x)


    parser.add_argument("--int_or_off", type=int_or_off)

Specifying a class as the type conflicts with the signature and type hint
support that is central to jsonargparse. Therefore, providing a class as the
type does not work the same way as in argparse. The recommended alternative is
to implement a custom type; see :ref:`custom-types`.


.. _logging:

Troubleshooting and logging
===========================

The standard behavior for the parse methods, when they fail, is to print a short
message and terminate the process with a non-zero exit code. This is problematic
during development since there is not enough information to track down the root
of the problem. Without the need to change the source code, this default
behavior can be changed such that in case of failure, a ParseError exception is
raised and the full stack trace is printed. This is done by setting the
``JSONARGPARSE_DEBUG`` environment variable to ``true``.

The parsers from jsonargparse log some basic events, though by default this is
disabled. To enable, the ``logger`` argument should be set when creating an
:class:`.ArgumentParser` object. The intended use is to provide an already
existing logger object which is used for the whole application. For convenience,
to enable a default logger the ``logger`` argument can also be ``True`` or
a string which sets the name of the logger or a dictionary that can include the
name and the level, e.g. ``{"name": "myapp", "level": "ERROR"}``.
