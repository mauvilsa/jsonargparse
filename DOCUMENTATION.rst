.. _auto-cli:

Basic usage
===========

There are two ways of using jsonargparse. One is to build a parser step by step
(see :ref:`parsers`), which is almost a drop-in replacement of argparse. But
argparse is verbose and duplicates information that the code already has. The
simpler and recommended way is the :func:`.auto_cli` function, which builds the
parser from the signatures of the given functions and classes. For example:

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

The ``name`` and ``prize`` parameters have type hints and are described in the
docstring. Both are shown in the help. In a shell:

.. code-block:: bash

    $ python example.py --help
    ...
    Prints the prize won by a person:
      name                  Name of winner. (required, type: str)
      --prize PRIZE         Amount won. (type: int, default: 100)

    $ python example.py Lucky --prize=1000
    Lucky won 1000€!

.. note::

    Parsing of docstrings is optional. For the help to show the descriptions,
    install jsonargparse with the ``signatures`` extra, see :ref:`installation`.

Given a single class, the first arguments are the class init parameters, then
comes a method name (methods become :ref:`sub-commands`), and then the
parameters of that method:

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

In a shell:

.. code-block:: bash

    $ python example.py --max_prize=1000 person Lucky
    Lucky won 632€!

.. doctest:: :hide:

    >>> auto_cli(Main, args=["--max_prize=1000", "person", "Lucky"])  # doctest: +ELLIPSIS
    'Lucky won ...€!'

If the class has no public methods, there are no subcommands and
:func:`.auto_cli` returns an instance of the class:

.. testcode::

    from dataclasses import dataclass
    from jsonargparse import auto_cli


    @dataclass
    class Settings:
        name: str
        prize: int = 100


    if __name__ == "__main__":
        print(auto_cli(Settings, as_positional=False))

In a shell:

.. code-block:: bash

    $ python example.py --name=Lucky
    Settings(name='Lucky', prize=100)

.. doctest:: :hide:

    >>> auto_cli(Settings, as_positional=False, args=["--name=Lucky"])  # doctest: +ELLIPSIS
    Settings(name='Lucky', prize=100)

Note the ``as_positional=False``, which makes required arguments non-positional.
To get an instance even when the class does have public methods, use
``return_instance=True``. Then only the init arguments are parsed and no method
subcommands are added.

If several functions are given, each one becomes a subcommand, i.e. ``example.py
function [arguments]``. If several classes are given, or a mix of classes and
functions, running a method needs two levels of subcommands, i.e. ``example.py
class [init_arguments] method [arguments]``.

A ``dict`` defines subcommands with custom names and any number of levels:

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

In a shell:

.. code-block:: bash

    $ python example.py weekend tier1 Lucky
    Lucky won 300€!

.. doctest:: :hide:

    >>> auto_cli(components, args=["weekend", "tier1", "Lucky"])
    'Lucky won 300€!'

.. note::

    These examples only use ``str`` and ``int`` type hints. jsonargparse
    supports a much wider range of types, see :ref:`type-hints`. Classes can
    also be used as type hints, which makes configurable `dependency injection
    (object composition) <https://en.wikipedia.org/wiki/Dependency_injection>`__
    easy, see :ref:`sub-classes`.

Writing configuration files
---------------------------

Tools created with :func:`.auto_cli` have a ``--config`` option to give settings
in a config file (see :ref:`configuration-files`). This helps when there are
many parameters. The ``--print_config`` option prints all supported settings
with their default values, which is a good starting point:

.. code-block:: bash

    # Dump default config to have as reference
    python example.py --print_config > config.yaml
    # Modify the config as needed (all default settings can be removed)
    nano config.yaml
    # Run the tool using the adapted config
    python example.py --config config.yaml

.. _parsers:

Parsers
=======

A parser is created just like with Python's `argparse
<https://docs.python.org/3/library/argparse.html>`__: import the module, create
a parser and add arguments to it.

.. testcode::

    from jsonargparse import ArgumentParser

    parser = ArgumentParser(prog="app", description="Description for my app.")
    parser.add_argument("--opt1", type=int, default=0, help="Help for option 1.")
    parser.add_argument("--opt2", type=float, default=1.0, help="Help for option 2.")


:meth:`parse_args <.ArgumentParser.parse_args>` returns an object with the
parsed values, or the defaults, as attributes. In the examples a list of
arguments is given to it, instead of taking them from the command line:

.. doctest::

    >>> cfg = parser.parse_args(["--opt2", "2.3"])
    >>> cfg.opt1, type(cfg.opt1)
    (0, <class 'int'>)
    >>> cfg.opt2, type(cfg.opt2)
    (2.3, <class 'float'>)

If parsing fails, by default the usage is printed and the program exits. With
``exit_on_error=False`` an :class:`.ArgumentError` is raised instead.


Override order
--------------

Parsed values can come from several sources: the source code, command line
arguments, :ref:`configuration-files` and :ref:`environment-variables`. Later
sources in the following list override earlier ones:

1. Defaults defined in the source code.
2. Existing default config files in the order defined in
   ``default_config_files``, e.g. ``~/.config/myapp.yaml``.
3. Full config environment variable, e.g. ``APP_CONFIG``.
4. Individual key environment variables, e.g. ``APP_OPT1``.
5. Command line arguments in order left to right (might include config files).

Some of these sources might not apply, depending on the parse method used (see
:class:`.ArgumentParser`) and how the parser was built. Environment variables
must be enabled explicitly, except when using :meth:`parse_env
<.ArgumentParser.parse_env>`. Without an ``action="config"`` argument there is
no full config environment variable and no way to give a config file from the
command line.


Capturing parsers
-----------------

A common pattern is a single function that builds a parser, possibly depending
on some parameters, and then parses:

.. testcode::

    from jsonargparse import ArgumentParser


    def main_cli():
        parser = ArgumentParser()
        ...
        cfg = parser.parse_args()
        ...


    if __name__ == "__main__":
        main_cli()

Sometimes the parser object is needed without parsing. For instance
`sphinx-argparse <https://sphinx-argparse.readthedocs.io/en/stable/>`__
includes the help of CLIs in generated documentation, and requires a function
that returns the parser. :func:`.capture_parser` provides it:

.. testcode::

    from jsonargparse import capture_parser


    def get_parser():
        return capture_parser(main_cli)

.. note::

    For tools based on :func:`.auto_cli`, the way to get the parser is
    :func:`.auto_parser`, a shorthand that calls :func:`.capture_parser`.


Optionals as positionals
------------------------

Optional arguments can be accepted both by name, e.g. ``--key=val``, and as
positional, e.g. ``val``. Enable this with
``set_parsing_settings(parse_optionals_as_positionals=True)``. Key points:

- Only optionals that take exactly one value qualify, i.e. no ``nargs`` or
  ``nargs=1``.
- Optionals with subclass types are excluded.
- Extra positional values are assigned after the real positionals, in the order
  in which the optionals were added to the parser. The usage in the help shows
  which optionals accept this and in which order.
- In a parser with subcommands, only the subparsers support this, after the
  subcommand name(s) are given.

For instance, for a parser defined as:

.. testcode::

    from jsonargparse import set_parsing_settings


    set_parsing_settings(parse_optionals_as_positionals=True)

    parser.add_argument("p1")
    parser.add_argument("--o2")
    parser.add_argument("--o3")

the help shows ``p1 [o2 [o3]]`` and a note saying that the feature is enabled.
Giving values by name still works, e.g. ``--o2=val2 --o3=val3 val1``. Also valid
are ``--o3=val3 val1 val2`` and ``val1 val2 val3``.

.. note::

    Positionals take precedence. If a value is given both ways, the positional
    one is used, no matter the order. With the parser above, ``val1 val2a
    --o2=val2b`` gives ``o2=val2a``.


Always fail arguments
---------------------

The :class:`.ActionFail` action adds an argument that always fails when given. A
use case is a feature that is only available if some package is installed:

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

Then giving ``--module=...``, or a nested form like ``--module.child=...``,
fails with the configured message. The message accepts the ``%(option)s`` and
``%(value)s`` placeholders.


.. _unset-values:

Unset values
------------

By default jsonargparse follows argparse: an argument that is not given gets the
value ``None``. This makes it impossible to tell apart an argument that was
explicitly set to ``None``, e.g. ``--opt=null``, from one that was simply not
given.

``set_parsing_settings(unset_sentinel=True)`` solves this by using the
:obj:`.Unset` sentinel as the default of the arguments that were not given a
``default``. An argument then has three possible states:

- :obj:`.Unset` – not given, and ``add_argument`` received no ``default``.
- ``None`` – either explicitly set to ``null``, or ``add_argument`` received
  ``default=None``.
- Any other value – the given value, or the default.

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

.. testcleanup:: unset-values

    set_parsing_settings(unset_sentinel=False)

The ``skip_unset`` parameter of :meth:`dump <.ArgumentParser.dump>`, :meth:`save
<.ArgumentParser.save>` and :meth:`validate <.ArgumentParser.validate>` decides
whether :obj:`.Unset` entries are excluded, and defaults to ``True``. From the
command line the same is done with ``--print_config=skip_unset``.

**Relation to** ``argument_default=SUPPRESS``

Argparse's ``argument_default=SUPPRESS``, and the per-argument
``default=SUPPRESS``, are complementary: an argument that is not given is
**completely absent** from the namespace, i.e. it has no key at all. The two
features work well together and express different levels of absence.


.. _type-hints:

Type hints
==========

jsonargparse supports a wide range of argument types and validates values
against them, using Python's type hint syntax. For example, an argument that
accepts ``None``, a float in the range ``(0, 1)``, or a positive int:

.. testcode::

    from jsonargparse.typing import PositiveInt, OpenUnitInterval

    parser.add_argument("--op", type=PositiveInt | OpenUnitInterval | None)

The types in :py:mod:`jsonargparse.typing` are a convenience for cases that
standard Python does not cover. Using them is not required.

Types can be nested with any complexity. Notes about the support:

- Nested types, i.e. child types inside ``list``, ``dict``, etc., work as long
  as at least one child type is supported. There is no limit in nesting depth.

- Supported PEPs: `563 <https://peps.python.org/pep-0563/>`__ postponed
  evaluation (``from __future__ import annotations``), `585
  <https://peps.python.org/pep-0585/>`__ (``list[<type>]`` instead of
  ``List[<type>]``) and `604 <https://peps.python.org/pep-0604/>`__ (``<type> |
  <type>`` instead of ``Union[<type>, <type>]``).

- Types that use components imported inside ``TYPE_CHECKING`` blocks work, and
  so do forward references, including names defined only in the body of the
  class that owns the method, e.g. a nested class referred to without qualifying
  it.

- Fully supported types are: ``str``, ``bool`` (see :ref:`boolean-arguments`),
  ``int``, ``float``, ``Decimal``, ``complex``, ``bytes``/``bytearray`` (Base64
  encoding), ``range``, ``list`` (see :ref:`list-append`), ``Deque``,
  ``Iterable``, ``Sequence``, ``MutableSequence``, ``Collection``,
  ``Container``, ``Reversible``, ``Any``/``object``, ``Union``/``Optional`` (see
  :ref:`union-types`), ``Literal``, ``Type``, ``Enum``, ``PathLike``, ``UUID``,
  ``timedelta``, the restricted types of :ref:`restricted-numbers` and
  :ref:`restricted-strings`, and the path and URL types of :ref:`parsing-paths`
  and :ref:`parsing-urls`.

- ``dict``, ``Mapping``, ``MutableMapping``, ``MappingProxyType``,
  ``OrderedDict`` and ``TypedDict`` are supported, but only with ``str`` or
  ``int`` keys, see :ref:`dict-items`.

- ``TypedDict`` accepts ``Required`` and ``NotRequired`` to mark single keys as
  required or optional, and ``Unpack`` to type ``**kwargs`` precisely, see PEP
  `692 <https://peps.python.org/pep-0692/>`__. A ``--*.help`` option, e.g.
  ``--data.help``, shows the accepted keys. It takes no value, unless the
  ``TypedDict`` is in a union with other types that have their own help, in
  which case the value is the name of the typed dict, e.g. ``--data.help
  SomeTypedDict``. :meth:`add_class_arguments
  <.ArgumentParser.add_class_arguments>` also accepts a ``TypedDict``, adding
  one argument per key and giving the corresponding dict on :meth:`instantiate
  <.ArgumentParser.instantiate>`. As the argument of ``type``, e.g.
  ``type[SomeTypedDict]``, the value is an import path to a class. Since
  ``TypedDict`` classes don't support ``issubclass``, the given class is
  accepted when it is structurally compatible, as specified in PEP `589
  <https://peps.python.org/pep-0589/>`__, i.e. it has all the expected keys with
  the same types and requiredness. A generic ``TypedDict`` works both
  unsubscripted and subscripted, e.g. ``SomeDict`` and ``SomeDict[int]``, as
  does one that inherits from a subscripted one. Subscripting doesn't change
  which keys are accepted, only the types of the keys annotated with a
  ``TypeVar``. A key whose type can't be validated accepts any value, see
  :ref:`unvalidated-types`.

- ``tuple``, ``set``, ``frozenset``, ``AbstractSet`` and ``MutableSet`` are
  supported, even though on the command line, in config files and in environment
  variables they are all written as an array, like a ``list``. Each ``tuple``
  position can have its own type, which is validated as such, and ``tuple[type,
  ...]`` is also accepted. A ``set`` or ``frozenset`` of a class type is kept as
  a list when parsing, since subclass specs are not hashable, and becomes a set
  on :meth:`instantiate <.ArgumentParser.instantiate>`.

- ``None`` is written as ``null``, as JSON/YAML define it. For the same reason
  the help shows ``NoneType`` as ``null``, e.g. a parameter with type and
  default ``Optional[str] = None`` is shown as ``type: Union[str, null],
  default: null``.

- Normal classes can be used as a type. The value is a dict with a
  ``class_path`` and optionally ``init_args``, and :meth:`instantiate
  <.ArgumentParser.instantiate>` instantiates all classes in a config object,
  see :ref:`sub-classes`.

- ``Protocol`` types work the same as subclasses and don't need to be
  ``runtime_checkable``. An accepted class must implement all public methods of
  the protocol with a compatible signature, i.e. be callable in every way that
  the protocol's methods can be called, like static type checkers verify.
  Parameter and return types must match exactly, subtypes are not accepted,
  except where the protocol has no annotation or ``Any``, which accept any type.
  A generic protocol works both unsubscripted and subscripted, e.g. ``Proto``
  and ``Proto[int]``. Subscripting substitutes the type arguments in the
  protocol's methods, so ``Proto[int]`` and ``Proto[str]`` accept different
  implementations. A ``TypeVar`` that remains, in the protocol or in the
  implementation, matches any type, as static type checkers do. A protocol whose
  only method is ``__call__`` is also implemented by a function with a
  compatible signature, in which case the value is the function itself, instead
  of a class to instantiate.

- ``dataclasses``, final classes, attrs' ``define``, pydantic's ``dataclass``
  and pydantic's ``BaseModel`` are supported, even when nested. By default they
  don't accept subclasses, see :ref:`subclasses-disabled` and
  :ref:`enable-disable-subclasses`. A dataclass that also inherits from a normal
  class does accept subclasses by default.

- User-defined ``Generic`` types are supported, see :ref:`generic-types`.

- ``Annotated`` types are supported. If the metadata is a `pydantic type
  <https://docs.pydantic.dev/latest/api/types/>`__, it is used for validation.

- ``pydantic.SecretStr`` is supported and, as expected, the actual value is not
  serialized. ``jsonargparse.typing.SecretStr`` gives the same behavior without
  the pydantic dependency. Dumps only have the mask ``**********``, and parsing
  this mask as a secret fails, so that a config bootstrapped with
  ``--print_config`` is not used with the mask as the secret.

- ``pydantic.FilePath`` and ``pydantic.DirectoryPath`` run the corresponding
  pydantic validation when parsing. Arguments with these types also get file and
  directory tab completions, see :ref:`tab-completion`.

- ``Callable`` accepts either a dot import path to a callable object, or a dict
  with ``class_path`` and optionally ``init_args``. The named class must either
  instantiate into a callable or be a subclass of the callable's return type.
  :meth:`instantiate <.ArgumentParser.instantiate>` then gives the instance or a
  function that returns it, see :ref:`callable-type`. A function given by import
  path must have a return annotation, or a return type in a stub file (see
  :ref:`stubs-resolver`), that is the callable's return type or a subclass of
  it. Argument types are not validated.

- ``types.ModuleType`` accepts the dot import path of a module, and on
  ``instantiate`` is replaced by the imported module object.

- ``types.UnionType`` and ``types.GenericAlias``, commonly found in third party
  libraries in unions such as ``type | UnionType | dict``, accept a string with
  a type expression, e.g. ``"int | str"`` or ``"list[int]"``. The expression is
  resolved without evaluating code, so its names must be builtins, ``typing``
  names or dot import paths.

- ``TypeAliasType`` is supported. Values are parsed as the aliased type and the
  help shows the alias as the argument type. This includes aliases defined with
  the `PEP 695 <https://peps.python.org/pep-0695/>`__ ``type X = ...`` statement
  (Python 3.12+) and aliases created with ``typing_extensions.TypeAliasType``.


.. _union-types:

Union types
-----------

A value for an argument with a ``Union`` type is validated against each subtype,
one at a time, and the first subtype that accepts it decides the parsed value.
So the order of the subtypes matters. For example, for ``Union[str, int]`` the
command line value ``2`` is parsed as the ``str`` ``"2"``, since any command
line value is a valid ``str``, whereas for ``Union[int, str]`` it is parsed as
the ``int`` ``2``.

Subtypes are mostly attempted in the order in which they are written. The
exception are the ones that accept anything, which are moved to the end when the
argument is added, so that the subtypes that do validate get a chance. From
first to last attempted, the groups are:

1. All types not mentioned below, in the order in which they are written.
2. ``None``, which only accepts ``null``. It is placed second to last so that
   ``Optional[<type>]`` reads in the help as it does in the source code.
3. ``Any``, ``object`` and the types that can't be validated, see
   :ref:`unvalidated-types`. These accept any value, so a subtype after them
   would never be attempted.

The sorting is stable, so subtypes in the same group keep their relative order.
Unions nested inside other types are sorted as well, e.g. the ``Union`` in
``list[Union[int, Any]]``.

Be aware that ``typing`` considers two unions equal no matter the order of the
subtypes, and caches the types that it creates. So for a union nested in a
``typing`` type, e.g. ``typing.List[Union[int, str]]``, the order can end up
being the one of an equal union created earlier somewhere else. `PEP 585
<https://peps.python.org/pep-0585/>`__ types are not cached, so
``list[Union[int, str]]`` always keeps the order as written.

The sorting happens when the argument is added, so the type shown in ``--help``
is the sorted one. That is, the help always tells in which order the subtypes
are attempted. For example, an argument added as:

.. testsetup:: union

    from typing import Any, Union

    parser = ArgumentParser(exit_on_error=False)

.. testcode:: union

    parser.add_argument("--val", type=Union[Any, int, None])

is shown in the help as ``(type: Union[int, null, Any], default: null)`` and
parses values as:

.. doctest:: union

    >>> parser.parse_args(["--val=2"])
    Namespace(val=2)
    >>> parser.parse_args(["--val=null"])
    Namespace(val=None)
    >>> parser.parse_args(["--val=abc"])
    Namespace(val='abc')

In one case the order changes while parsing instead of when the argument is
added: when appending to a list, see :ref:`list-append`, the subtypes that are a
list are moved to the front. This can only be decided when parsing, since it
depends on whether the value is appended to a previous list or replaces it. For
an argument of type ``Union[int, list[int]]``, ``--val=1`` gives ``1``, while
``--val+=1`` gives ``[1]``.


.. _unvalidated-types:

Unvalidated types
-----------------

A :ref:`signature parameter <classes-methods-functions>` or a ``TypedDict`` key
can have a type that jsonargparse can't validate. The argument is still added,
with only the parts of the type that can't be validated replaced by a type that
accepts any value. The help shows these parts as ``Unvalidated<...>``, keeping
the name used in the source code. For example, a class with a parameter
``items: list[SomeType] = []`` for which ``SomeType`` can't be validated is
shown in the help as:

.. code-block:: text

    --myclass.items ITEMS  (type: list[Unvalidated<SomeType>], default: [])

Only these parts accept any value: in the example the value must still be a
list, and in a ``Union`` the other subtypes are still validated. A type or a
part of it can't be validated when:

- It failed to resolve, e.g. a missing import or a typo in a postponed
  annotation.
- It is not a type that jsonargparse supports, e.g. a ``TypeVar`` that stands
  for nothing, see :ref:`generic-types`.

The debug log gives the reason for each part, see :ref:`logging`. A parameter
without a type annotation is shown as ``Untyped`` and behaves the same, see
:ref:`classes-methods-functions`.

Since there is no type to serialize with, :meth:`dump <.ArgumentParser.dump>`
and ``--print_config`` derive a type from the value itself. A value of a type
that jsonargparse doesn't support, e.g. an arbitrary object, is serialized like
the instances given for a :ref:`subclass type <sub-classes>`: as an import path
when it can be imported back, and otherwise as a message saying that it was not
serializable, together with a warning.

Parsing a dump back has no type to validate with either, so only the values that
the config formats represent round-trip, e.g. a ``set`` is dumped and parsed
back as a list, and an ``Enum`` member as its name. A warning is raised for each
dumped value that loses its type this way. All of the above applies equally to
``Any`` and ``object``.


.. _restricted-numbers:

Restricted numbers
------------------

Numbers often need a limited range. For the common cases ``jsonargparse.typing``
has the predefined types :class:`.PositiveInt`, :class:`.NonNegativeInt`,
:class:`.PositiveFloat`, :class:`.NonNegativeFloat`,
:class:`.ClosedUnitInterval` and :class:`.OpenUnitInterval`, and the
:func:`.restricted_number_type` function to define new ones:

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

Likewise, :func:`.restricted_string_type` creates string types restricted to
match a regular expression. The predefined ones are :class:`.Email`, which
follows the normal email pattern, and :class:`.NotEmptyStr`. For example, an
argument that must be exactly four uppercase letters:

.. testcode::

    from jsonargparse.typing import Email, restricted_string_type

    CodeType = restricted_string_type("CodeType", "^[A-Z]{4}$")
    parser.add_argument("--code", type=CodeType)
    parser.add_argument("--email", type=Email)


.. _parsing-paths:

Parsing paths
-------------

Parsing a file path often means checking that it exists and has the required
access permissions, without opening the file. Also, a path in a config file can
be relative to the location of that config file, and after parsing it should be
easy to use without having to think about where the config file was. For this
jsonargparse has the :func:`.path_type` type generator and some predefined
types, e.g. :class:`.Path_fr`.

For example, suppose there is a directory with a config file ``app/config.yaml``
and some data ``app/data/info.db``. The YAML file contains:

.. code-block:: yaml

    # File: config.yaml
    databases:
      info: data/info.db

To check that ``databases.info`` is a file that exists and is readable:

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

The ``fr`` in the type name are flags standing for file and readable. After
parsing, ``databases.info`` is a :class:`.Path_fr` instance, which gives both
the original relative path from the YAML file and the absolute path:

.. doctest:: paths
    :skipif: os.name != "posix"

    >>> cfg.databases.info.relative
    'data/info.db'
    >>> cfg.databases.info.absolute  # doctest: +ELLIPSIS
    '/.../app/data/info.db'

Directories work the same, e.g. :class:`.Path_dw` requires a directory that
exists and is writable. New path types are created with :func:`.path_type`, e.g.
``Path_frw = path_type('frw')`` for files that must exist and be both readable
and writable. If ``app/config.yaml`` is not writable, then
``Path_frw('app/config.yaml')`` raises a ``PathError`` (a subclass of
``TypeError``) saying that the file is not writable. All supported mode flags
are documented in the :class:`.Path` class.

Types created with :func:`.path_type` have :class:`.Path` as base class. This
class implements the ``os.PathLike`` protocol, using the absolute path, so for
the previous example:

.. doctest:: paths
    :skipif: os.name != "posix"

    >>> os.fspath(cfg.databases.info)  # doctest: +ELLIPSIS
    '/.../app/data/info.db'

The content of the file is read with the :py:meth:`.Path.read_text` method, e.g.
``info_db = cfg.databases.info.read_text()``.

An argument with a path type can be given ``nargs='+'`` to accept multiple
paths, i.e. ``--files file1 file2``. To instead read a list of paths from a
plain text file or from stdin, add the argument with type ``list[<path_type>]``
and ``sub_configs=True``. The special string ``'-'`` means stdin:

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

Without ``nargs``, the argument expects a single value. So giving several paths
directly on the command line requires the YAML/JSON array syntax, i.e. ``--list
"[file1,file2]"``, or the simpler append syntax of :ref:`list-append`, i.e.
``--list+ file1 --list+ file2``. Not as short as ``nargs='+'``, but with tab
completion the effort is minimal.

The same ``list[<path_type>]`` behavior applies to arguments created
automatically from type hints in signatures, i.e. with :func:`.auto_cli`,
:meth:`add_function_arguments <.ArgumentParser.add_function_arguments>`,
:meth:`add_method_arguments <.ArgumentParser.add_method_arguments>`,
:meth:`add_class_arguments <.ArgumentParser.add_class_arguments>` and
:meth:`add_subclass_arguments <.ArgumentParser.add_subclass_arguments>`.

.. note::

    Setting both ``nargs='+'`` and ``sub_configs=True`` for an argument of type
    ``list[<path_type>]`` makes each given value produce a list of paths, which
    might not be what you expect.

.. note::

    Not all features of the :class:`.Path` class are supported on Windows.


.. _parsing-urls:

Parsing URLs
------------

:func:`.path_type` also supports URLs, with the ``'u'`` flag, and `fsspec
<https://filesystem-spec.readthedocs.io>`__ file systems, with the ``'s'`` flag.
These need the *requests* and *fsspec* packages, which are installed with the
``urls`` and ``fsspec`` extras, see :ref:`installation`.

For example, an argument that accepts either a readable file or a URL uses the
type ``Path_fur = path_type('fur')``. If the value looks like a URL, a HEAD
request checks that it is accessible. The :py:meth:`.Path.read_text` method then
gets the content, doing a GET request for a URL, so the code does not need to
care whether the value is a local file or a URL.

``set_parsing_settings(config_read_mode_urls_enabled=True)`` and
``set_parsing_settings(config_read_mode_fsspec_enabled=True)`` extend this to
config files, that is to :meth:`parse_path <.ArgumentParser.parse_path>`,
:meth:`get_defaults <.ArgumentParser.get_defaults>` (``default_config_files``
argument), ``action="config"``, :py:meth:`.FromConfigMixin.from_config`,
:class:`.ActionJsonSchema`, :class:`.ActionJsonnet` and :class:`.ActionParser`.
So a tool that takes a config file can also get it from a URL:

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

Boolean arguments are very common, but argparse only supports them through
``store_true`` and ``store_false``. Users new to argparse often write
``type=bool``, which in argparse does not do what they expect.

In jsonargparse ``type=bool`` does the expected thing: the values ``true`` and
``yes`` parse as ``True``, and ``false`` and ``no`` as ``False``. For example:

.. testsetup:: boolean

    parser = ArgumentParser()

.. doctest:: boolean

    >>> parser.add_argument("--op1", type=bool, default=False)  # doctest: +IGNORE_RESULT
    >>> parser.add_argument("--op2", type=bool, default=True)  # doctest: +IGNORE_RESULT
    >>> parser.parse_args(["--op1", "yes", "--op2", "false"])
    Namespace(op1=True, op2=False)

Two paired options, one to set ``True`` and the other to set ``False``, are
added with :class:`.ActionYesNo`:

.. testsetup:: yes_no

    parser = ArgumentParser()

.. testcode:: yes_no

    from jsonargparse import ActionYesNo

    # --op1 for true and --no_op1 for false.
    parser.add_argument("--op1", action=ActionYesNo)
    # --with-op2 for true and --without-op2 for false.
    parser.add_argument("--with-op2", action=ActionYesNo(yes_prefix="with-", no_prefix="without-"))

With ``nargs='?'`` these options also accept a value of ``true``, ``yes``,
``false`` or ``no``.


.. _enums:

Enum arguments
--------------

String choices are another case of restricted values. Besides the usual
``choices`` list, an ``Enum`` class can be given as type, which has the benefit
of mapping each string to a desired value:

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

By default a new value replaces the previous one, also for lists. So
``parser.parse_args(['--list=[1]', '--list=[2, 3]'])`` gives ``[2, 3]``. To
append instead of replace, add ``+`` as suffix to the argument name:

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

Config files support this too. The following two files first assign a list and
then append to it:

.. code-block:: yaml

    # config1.yaml
    list:
    - 1

.. code-block:: yaml

    # config2.yaml
    list+:
    - 2
    - 3

Appending works for any element type. When the type is a union that has a list
among its subtypes, appending changes the order in which the subtypes are
attempted, see :ref:`union-types`. Lists of class types (see :ref:`sub-classes`)
also work: first append the class with the ``+`` suffix, then give its
``init_args`` as if the type were not a list, since they apply to the last class
in the list. For example, for an argument added as:

.. testcode:: append

    parser.add_argument("--list_of_instances", type=list[MyBaseClass])

Thanks to the short notation, ``class_path`` and ``init_args`` can be omitted,
so several classes are appended and configured as:

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

Once a new class is appended, the arguments of a previous class can no longer be
changed. This limitation is intentional: it forces classes and their arguments
to be given in order, which makes the command line easier to write and to read.


.. _dict-items:

Dict items
----------

An argument of type ``dict`` accepts a value in JSON format:

.. testsetup:: dict_items

    parser = ArgumentParser()

.. doctest:: dict_items

    >>> parser.add_argument("--dict", type=dict)  # doctest: +IGNORE_RESULT
    >>> parser.parse_args(['--dict={"key1": "val1", "key2": "val2"}'])
    Namespace(dict={'key1': 'val1', 'key2': 'val2'})

As with lists, a second JSON dict replaces the previous value completely.
Single items are set without replacing as:

.. doctest:: dict_items

    >>> parser.parse_args(["--dict.key1=val1", "--dict.key2=val2"])
    Namespace(dict={'key1': 'val1', 'key2': 'val2'})


.. _generic-types:

Generic types
-------------

Classes that inherit from ``typing.Generic``, i.e. `user-defined generic types
<https://docs.python.org/3/library/typing.html#user-defined-generic-types>`__,
are supported. For example, a point in 2D:

.. testsetup:: generic_types

    parser = ArgumentParser()

.. testcode:: generic_types

    from typing import Generic, TypeVar

    Number = TypeVar("Number", float, complex)

    @dataclass
    class Point2d(Generic[Number]):
        x: Number = 0.0
        y: Number = 0.0

Parsing complex-valued points:

.. doctest:: generic_types

    >>> parser.add_argument("--point", type=Point2d[complex])  # doctest: +IGNORE_RESULT
    >>> parser.parse_args(["--point.x=(1+2j)"]).point
    Namespace(x=(1+2j), y=0.0)

A ``TypeVar`` can't be used to validate, so when it is used as a type, e.g.
``options: Optional[OptionsT] = None``, it is replaced by what it stands for:
its PEP 696 ``default``, its constraints or its bound, in that order. Any of
these given as a forward reference, e.g. ``TypeVar("OptionsT",
default="Options[int]")``, is resolved with the names of the module in which the
``TypeVar`` is defined. When the ``TypeVar`` has none of these, or the forward
reference fails to resolve, the value is accepted without validation and the
help shows it as ``Unvalidated<...>``.


.. _callable-type:

Callable type
-------------

A ``Callable`` type accepts several kinds of value. The first is the import path
of a callable object:

.. testsetup:: callable

    parser = ArgumentParser()

.. testcode:: callable

    parser.add_argument("--callable", type=Callable)
    parser.parse_args(["--callable=time.sleep"])

The second is a class whose instances are callable:

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

The third only applies when the callable returns class instances. It is a form
of :ref:`dependency-injection`, explained in :ref:`instance-factories`.

.. _registering-types:

Registering types
-----------------

:func:`.register_type` adds new types for use in parsers. If the class can be
created from a string representation, and ``str`` of an instance gives that
representation back, only the class is needed. This is how
``jsonargparse.typing`` registers complex numbers, ``register_type(complex)``,
which is the same as ``register_type(complex, serializer=str,
deserializer=complex)``. Other classes need a serializer and/or a deserializer,
for example ``datetime``:

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

Registering an already registered type replaces the previous one, jsonargparse's
own registrations included. A debug log names the module of each, useful when
two packages register the same type. Give ``fail_already_registered=True`` to
fail instead. A generic class is registered unsubscripted, and the registration
also applies to its subscripted forms, e.g. ``os.PathLike[str]``. The type
arguments are not validated, since the deserializer gets the complete value.

.. note::

    Registering is only intended for simple types. By default, any class used as
    a type hint is treated as a subclass type (see :ref:`sub-classes`), which
    suits many use cases. Registering a class with :func:`.register_type`
    removes that option.


.. _custom-types:

Creating custom types
---------------------

New types can be created and used for parsing. Even when a type is meant for a
CLI, it is better to design it so that it also makes sense outside of parsing,
i.e. as a type hint in functions and classes that improves the code in general.
An alternative is to use `pydantic types
<https://docs.pydantic.dev/latest/api/types/>`__.

The simplest way is to implement a class. Take a basic type such as ``int`` as
reference. Basic types have these properties:

- Casting a string creates an instance of the type, if the value is valid, e.g.
  ``int("1")``.
- Casting a string raises a ``ValueError``, if the value is not valid, e.g.
  ``int("a")``.
- Casting an instance of the type to string gives back the string representation
  of the value, e.g. ``str(1) == "1"``.
- Types are idempotent, i.e. casting an instance of the type to the type gives
  back the same value, e.g. ``int(1) == int(int(1))``.

A new type is registered with :func:`.register_type`. If it follows the
properties above, ``register_type(MyType)`` is enough. :func:`.extend_base_type`
creates and registers a type in a single call, for example for even integers:

.. testcode::

    from jsonargparse.typing import extend_base_type

    def is_even(class_type, value):
        if int(value) % 2 != 0:
            raise ValueError(f"{value} is not even")

    EvenInt = extend_base_type("EvenInt", int, is_even)

Then in a parser:

.. doctest::

    >>> parser = ArgumentParser()
    >>> parser.add_argument("--even_int", type=EvenInt)  # doctest: +IGNORE_RESULT
    >>> parser.parse_args(["--even_int=2"])
    Namespace(even_int=2)

When a custom type is used as a type hint, the default must be cast to it so
that static type checkers don't complain:

.. testcode::

    def fn(value: EvenInt = EvenInt(2)):
        ...


.. _nested-namespaces:

Nested namespaces
=================

Unlike in argparse, dot notation in the argument names defines a hierarchy of
nested namespaces:

.. doctest::

    >>> parser = ArgumentParser(prog="app")
    >>> parser.add_argument("--lev1.opt1", default="from default 1")  # doctest: +IGNORE_RESULT
    >>> parser.add_argument("--lev1.opt2", default="from default 2")  # doctest: +IGNORE_RESULT
    >>> cfg = parser.get_defaults()
    >>> cfg.lev1.opt1
    'from default 1'
    >>> cfg.lev1.opt2
    'from default 2'

A dataclass creates a group of nested options, with the advantage that the same
options can be reused in several places of a project. The analogous example is:

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

The :class:`.Namespace` class extends the argparse one. Keys can be accessed
like in a dictionary, either one level at a time, e.g. ``cfg['lev1']['opt1']``,
or all at once, e.g. ``cfg['lev1.opt1']``. The :py:meth:`.Namespace.as_dict`
method gives the nested namespace as a nested dictionary.


.. _configuration-files:

Configuration files
===================

jsonargparse can parse configuration files (config files). The dot notation
hierarchy of the arguments (see :ref:`nested-namespaces`) defines the structure
expected in these files. The default format is YAML. To change it, use the
``parser_mode`` parameter of the parser, e.g.
``ArgumentParser(parser_mode="toml")``.

The :py:attr:`.ArgumentParser.default_config_files` property holds patterns of
config files to search for, e.g.
``ArgumentParser(default_config_files=['~/.myapp.yaml', '/etc/myapp.yaml'])``.
All matching files are parsed in the given order and override the defaults from
the source code. They are always parsed first, so any command line argument
overrides their values.

An argument can also be added to give a config file path explicitly. This does
not disable ``default_config_files``. The config argument is parsed at its
position among the command line arguments, so arguments after it override the
values from that config file. It can be given several times, each one overriding
the previous. Using the example parser from :ref:`nested-namespaces`, a config
file in YAML format could be:

.. code-block:: yaml

    # File: example.yaml
    lev1:
      opt1: from yaml 1
      opt2: from yaml 2

Adding a config file argument and parsing some arguments then gives:

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

The value can also be a string with the config content, instead of a path:

.. doctest:: config

    >>> cfg = parser.parse_args(["--config", '{"lev1":{"opt1":"from string 1"}}'])
    >>> cfg.lev1.opt1
    'from string 1'

The config file can also come from an environment variable, see
:ref:`environment-variables`. This variable is parsed first, so any other
argument given through an environment variable overrides it.

To parse a config file or a config string without parsing command line
arguments, use :meth:`parse_path <.ArgumentParser.parse_path>` or
:meth:`parse_string <.ArgumentParser.parse_string>`.

Serialization
-------------

Parsers that have an ``action="config"`` argument also get a ``--print_config``
option. It is useful for tools with many options, to create an initial config
file with all default values. The option accepts one or more flags separated by
comma, e.g. ``--print_config=comments,skip_default``:

- ``comments``: add the help descriptions as YAML comments. Requires the
  `ruamel.yaml <https://pypi.org/project/ruamel.yaml>`__ package. The comments
  are the descriptions of the groups and arguments of the parser and, for values
  that correspond to a class, e.g. the ``init_args`` of a subclass or the fields
  of a dataclass, the descriptions from that class.
- ``skip_default``: skip entries whose value is the same as the default.
- ``skip_unset``: skip entries that were not given a value, see
  :ref:`unset-values`.

From Python, a config object is serialized with the :meth:`dump
<.ArgumentParser.dump>` and :meth:`save <.ArgumentParser.save>` methods. The
supported formats are ``yaml``, ``toml``, ``json``/``json_compact``,
``json_indented`` and ``parser_mode``, the default, which uses the format of the
parser. More formats are added with :func:`.set_dumper`, for example to dump
with PyYAML's ``default_flow_style``:

.. testcode::

    import yaml
    from jsonargparse import set_dumper


    def custom_yaml_dump(data):
        return yaml.safe_dump(data, default_flow_style=True)


    set_dumper("yaml_custom", custom_yaml_dump)

.. _custom-loaders:

Custom loaders
--------------

The ``yaml`` parser mode (see :py:meth:`.ArgumentParser.__init__`) loads with a
subclass of `yaml.SafeLoader
<https://pyyaml.org/wiki/PyYAMLDocumentation#loader>`__ that has three
differences:

- Float scientific notation is supported, e.g. ``'1e-3'`` gives ``0.001``, while
  default PyYAML gives the string ``'1e-3'``.
- Dates are kept as strings, e.g. ``'2020-01-01'``, while default PyYAML gives a
  ``datetime.date``.
- Text that looks like a mapping only because of the syntax is kept as a string,
  e.g. ``'{text}'`` and ``'name:'``, while default PyYAML gives ``{'text':
  None}`` and ``{'name': None}``.

The :func:`.set_loader` function replaces the ``yaml`` loader or adds a loader
as a new parser mode. For example, a custom PyYAML loader is registered and used
as:

.. testcode::

    import yaml
    from jsonargparse import ArgumentParser, set_loader


    class CustomLoader(yaml.SafeLoader):
        ...


    def custom_yaml_load(stream):
        return yaml.load(stream, Loader=CustomLoader)


    set_loader("yaml_custom", custom_yaml_load)

    parser = ArgumentParser(parser_mode="yaml_custom")

When the loader is based on a library other than PyYAML, give the ``exceptions``
that it raises on failure to :func:`.set_loader`.


.. _classes-methods-functions:

Classes, methods and functions
==============================

Well written Python code gives type hints to its parameters and describes them
in the docstrings. Making such code configurable should not duplicate the types
and the descriptions. To avoid this, jsonargparse adds annotated parameters as
arguments automatically, see :meth:`add_function_arguments
<.ArgumentParser.add_function_arguments>`, :meth:`add_method_arguments
<.ArgumentParser.add_method_arguments>`, :meth:`add_class_arguments
<.ArgumentParser.add_class_arguments>` and :meth:`add_subclass_arguments
<.ArgumentParser.add_subclass_arguments>`.

Take for example a class with an init and a method with docstrings:

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

Both ``MyClass`` and ``mymethod`` are made configurable, the class instantiated
and the method run, as follows:

.. testcode:: class_method

    from jsonargparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_class_arguments(MyClass, "myclass.init")
    parser.add_method_arguments(MyClass, "mymethod", "myclass.method")

    cfg = parser.parse_args()
    myclass = MyClass(**cfg.myclass.init.as_dict())
    myclass.mymethod(**cfg.myclass.method.as_dict())


The :meth:`add_class_arguments <.ArgumentParser.add_class_arguments>` call adds
``myclass.init.foo``, with the description from the docstring, and makes it
required since it has no default. When parsed, it is validated against its type
hint, i.e. a dict whose values are ints or lists of ints. Since the init has
``**kwargs``, the keyword arguments of ``MyBaseClass`` are added too. Likewise,
the :meth:`add_method_arguments <.ArgumentParser.add_method_arguments>` call
adds ``myclass.method.bar`` as a required float and ``myclass.method.baz`` as an
optional boolean with default false.

Several classes added with :meth:`add_class_arguments
<.ArgumentParser.add_class_arguments>` are instantiated at once with
:meth:`instantiate <.ArgumentParser.instantiate>`. In the example above, ``cfg =
parser.instantiate(cfg)`` makes ``cfg.myclass.init`` an instance of ``MyClass``,
built from the parsed arguments.

All values can be given in a single config file (see
:ref:`configuration-files`). For convenience, the values of each argument group
created by an add signature method can also come from its own file. For the
example above, a general config file could be:

.. code-block:: yaml

    myclass:
      init: myclass.yaml
      method: mymethod.yaml

Then ``myclass.yaml`` and ``mymethod.yaml`` hold the settings for the class
instantiation and for the method call.

A wide range of type hints is supported for signature parameters, see
:ref:`type-hints`. Notes about the add signature methods:

- A parameter without a type annotation, or with a type that can only be
  validated in part, is added with a type that accepts any value, see
  :ref:`unvalidated-types`. Without an annotation but with a default, the type
  is ``Union[<type of the default>, Untyped]``, i.e. a value is converted to the
  default's type when it accepts it.

- ``fail_untyped`` decides which parameters without a type annotation raise an
  exception instead: the required ones with the default ``True``, all of them
  with ``"all"``, and none with ``False``. Positional-only parameters are always
  required. Use ``"all"`` only for code you own, since one untyped parameter of
  a dependency would make its signature impossible to add.

- Parameters whose name starts with ``_`` are considered internal and skipped,
  unless they are required.

- The ``skip`` parameter excludes arguments, e.g.
  ``parser.add_method_arguments(MyClass, 'mymethod', skip={'baz'})``.

.. note::

    The signatures support is intended to be non-intrusive. By design there is
    no need to inherit from a class, add decorators, or use special type hints
    and default values. Among other advantages, this makes it possible to use
    classes from third party libraries, which developers can't modify.

From config mixin
-----------------

:class:`.FromConfigMixin` adds a ``from_config`` class method, so that a class
can be instantiated directly from configuration values. It is useful for small
utilities that load constructor values from a dictionary or a config file in a
single call.

.. doctest::

    >>> from jsonargparse import FromConfigMixin
    >>> class Client(FromConfigMixin):
    ...     def __init__(self, host: str = "localhost", port: int = 80):
    ...         self.host = host
    ...         self.port = port
    >>> client = Client.from_config({"host": "api.local", "port": 8080})
    >>> (client.host, client.port)
    ('api.local', 8080)

See :class:`.FromConfigMixin` in the API reference for the complete behavior.

Docstring parsing
-----------------

Parameter descriptions in the help require the `docstring-parser
<https://pypi.org/project/docstring-parser/>`__ package, which is included in
the ``signatures`` extra, see :ref:`installation`.

Two options can be configured, both related to parsing speed. By default the
style is ``docstring_parser.DocstringStyle.AUTO``, which tries all supported
styles. If the codebase uses a single style, setting it is faster:

.. testcode:: docstrings

    from docstring_parser import DocstringStyle
    from jsonargparse import set_parsing_settings

    set_parsing_settings(docstring_parse_style=DocstringStyle.REST)

The second option is support for `attribute docstrings
<https://peps.python.org/pep-0257/#what-is-a-docstring>`__, i.e. literal strings
in the line after an attribute is defined. It is disabled by default, because
enabling it makes parsing slower even for classes that have none:

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

Docstrings are searched in the entire class inheritance chain. So inherited
parameters and attributes are documented in the help by the base class that
declares them, and the description of a group comes from the nearest class in
the method resolution order that has a docstring. Base classes that only provide
machinery, i.e. ``object``, ``abc.ABC``, ``typing.Generic``, ``enum.Enum``,
``pydantic.BaseModel`` and the like, are skipped, since their docstrings
describe themselves instead of the class being added to the parser.

.. testcleanup:: docstrings

    set_parsing_settings(docstring_parse_style=DocstringStyle.GOOGLE)
    set_parsing_settings(docstring_parse_attribute_docstrings=False)

Customization of arguments
--------------------------

Arguments added automatically from signatures give the developer limited control
over their behavior. To customize them, subclass the parser and override the
:meth:`add_argument <.ActionsContainer.add_argument>` method. For example,
``bool`` arguments need a ``true|false`` value on the command line. To use
:class:`.ActionYesNo` instead, in a CLI based on :func:`.auto_cli`:

.. testcode::

    from jsonargparse import ActionYesNo, ArgumentParser, auto_cli

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

Some functions return an instance of a class. :func:`.class_from_function` turns
such a function into a class that can be added to a parser, so that
:meth:`instantiate <.ArgumentParser.instantiate>` calls the function:

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

    :func:`.class_from_function` requires the function to have a return type
    annotation, which must be the class that it returns.

Classes created with :func:`.class_from_function` can be selected using
``class_path`` for :ref:`sub-classes`. For example, if
:func:`.class_from_function` is run in a module ``my_module`` as:

.. testcode:: class_from_function

    class_from_function(instantiate_myclass, name="MyClass")

Then the ``class_path`` of the created class is ``my_module.MyClass``.


Parameter resolvers
-------------------

There are three techniques for resolving signature parameters. The AST resolver,
which uses Python's `Abstract Syntax Trees (AST)
<https://docs.python.org/3/library/ast.html>`__ library, is tried first. The
assumptions resolver, based on assumptions about class inheritance, is the
fallback for when AST fails. The stubs resolver, which uses ``*.pyi`` stub
files, is applied on top of both.

Unresolved parameters
^^^^^^^^^^^^^^^^^^^^^

The resolvers make a best effort to find the correct names and types that the
parser should accept. Some cases are not supported yet, and some would be
impossible to support. For these there is the special ``dict_kwargs`` key, whose
entries are not validated when parsing but are used for class instantiation. The
name comes from the use cases in which ``**kwargs`` is only used as a dict, a
purpose that it also serves.

This section is about parameters whose *name* the resolvers can't determine. For
parameters that are resolved but have a type that can't be validated, see
:ref:`unvalidated-types`.

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

The value for ``bar`` is not validated, but the class is instantiated as
``MyClass(foo=1, bar=2)``.

Assumptions resolver
^^^^^^^^^^^^^^^^^^^^

The assumptions resolver only considers classes. When ``__init__`` has ``*args``
and/or ``**kwargs``, it assumes that these go directly to the parent class, i.e.
that ``__init__`` has a line like ``super().__init__(*args, **kwargs)``, and
blindly collects the ``__init__`` parameters of the parent classes. If the code
does not follow this pattern, the collected parameters are wrong. This is why it
is only a fallback for when the AST resolver fails.

.. _ast-resolver:

AST resolver
^^^^^^^^^^^^

The AST resolver reads the source code and works out how ``*args`` and
``**kwargs`` are used, so as to find more accepted parameters. Since code can do
endless things, only a few specific cases are supported, illustrated below. The
code does not need to look exactly like this. What matters is how ``*args`` and
``**kwargs`` are used, not the other parameters, the names of the variables, or
the complexity of unrelated code.

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

There can be other parameters besides ``*args`` and ``**kwargs``, so the
signatures above could be e.g. ``name(p1: int, k1: str = 'a', **kws)``. The
internal call can also have extra parameters, for example:

.. testcode::

    def calls_a_function(*args, **kwargs):
        a_function(*args, param=1, **kwargs)

``param`` is excluded from the resolved parameters, because it is hard coded.

Multiple calls that use ``**kwargs`` are supported, but with caveats:

.. testcode:: ast_resolver

    def conditional_calls(**kwargs):
        if condition_1:
            first_function(**kwargs)
        elif condition_2:
            second_function(**kwargs)
        else:
            third_function(**kwargs)

Parameters that have the same type hint and default in all calls behave
normally. When the calls disagree, the help shows the default as
``Conditional<ast-resolver> {DEFAULT_1, ...}``. The main difference is that
these parameters are not included in :meth:`get_defaults
<.ArgumentParser.get_defaults>` or in the output of ``--print_config``. This is
needed because the parser does not know which call will happen at runtime, and
including them would make :meth:`instantiate <.ArgumentParser.instantiate>` fail
with unexpected keyword arguments.

.. note::

    The resolvers log failures and unsupported cases. To see these logs, set the
    environment variable ``JSONARGPARSE_DEBUG`` to ``true``. The supported cases
    are limited, so please create issues asking for new ones. Note though that a
    very convoluted case can be a sign that the code needs refactoring.

.. _stubs-resolver:

Stubs resolver
^^^^^^^^^^^^^^

The stubs resolver uses the `typeshed-client
<https://pypi.org/project/typeshed-client/>`__ package to find parameters and
their type hints in stub files ``*.pyi``. To enable it, install jsonargparse
with the ``signatures`` extra, see :ref:`installation`.

Most of the Python standard library has its types in stubs, for example:

.. doctest:: stubs_resolver

    >>> from random import uniform

    >>> parser = ArgumentParser()
    >>> parser.add_function_arguments(uniform, "uniform")  # doctest: +IGNORE_RESULT
    >>> parser.parse_args(["--uniform.a=0.7", "--uniform.b=3.4"])
    Namespace(uniform=Namespace(a=0.7, b=3.4))

Without the stubs resolver, that :meth:`add_function_arguments
<.ArgumentParser.add_function_arguments>` call needs ``fail_untyped=False``, and
then ``a`` and ``b`` get ``Untyped`` instead of ``float``, so an invalid value
such as a string would not fail.

The defaults of parameters found only through stubs are not known. The help then
shows the default as ``Unknown<stubs-resolver>``, and these parameters are not
included in :meth:`get_defaults <.ArgumentParser.get_defaults>` or in the output
of ``--print_config``.

By default only ``*.pyi`` files are searched. To also search in ``*.py`` files,
use ``set_parsing_settings(stubs_resolver_allow_py_files=True)``.

.. _parameter-aliases:

Parameter aliases
^^^^^^^^^^^^^^^^^

Pydantic and attrs allow giving a field a name that is different from the
attribute name, an alias: pydantic's ``alias``/``validation_alias`` and attrs'
``alias``. The resolvers take these aliases into account, so that a parser
accepts the same names as the class itself.

When the framework accepts both names, e.g. a pydantic model with
``populate_by_name``, the alias is accepted as an additional option and config
key. The attribute name is the one used in the parsed namespace, in
``--print_config`` and in dumps:

.. doctest:: parameter_aliases

    >>> from pydantic import BaseModel, ConfigDict, Field

    >>> class Client(BaseModel):
    ...     model_config = ConfigDict(populate_by_name=True)
    ...     api_key: str = Field(default="", alias="key")
    ...

    >>> parser = ArgumentParser()
    >>> parser.add_class_arguments(Client, "client")  # doctest: +IGNORE_RESULT
    >>> parser.parse_args(["--client.key=abc"])
    Namespace(client=Namespace(api_key='abc'))

When the framework only accepts the alias, e.g. the same model without
``populate_by_name``, the alias is the name used everywhere, since giving the
attribute name would not instantiate the class as expected.

Aliases don't work for a parameter whose type is a subclasses-disabled type
added as a group of arguments, since then the name is a prefix of several
arguments instead of a single option string, so only the attribute name is
accepted. Enabling subclasses for the type, see
:ref:`enable-disable-subclasses`, makes it a single argument, and then its alias
is accepted too.


.. _dependency-injection:

Dependency injection
====================

Dependency injection is a design pattern that separates how objects are created
from how they are used, giving more loosely coupled programs, see the `wikipedia
article <https://en.wikipedia.org/wiki/Dependency_injection>`__. Supporting it
has been a design goal of jsonargparse.

In Python, dependency injection is done by:

- Using as type hint a class, such that the parameter accepts an instance of
  this class or any subclass, e.g. ``module: ModuleBaseClass``.
- Using as type hint a callable that returns an instance of a class, such that
  the parameter accepts a function for instantiation. This could be either using
  ``Callable``, e.g. ``module: Callable[[int], ModuleBaseClass]``, or a
  protocol, e.g. ``module: ModuleFactoryProtocol``.

.. _sub-classes:

Class type and subclasses
-------------------------

When a class is used as a type hint, the value is a dictionary with a
``class_path`` entry, which is the dot notation expression to import the class,
and optionally ``init_args`` to instantiate it. This dictionary is called a
**subclass spec**. When parsing, it is checked that the class can be imported,
that it is a subclass of the type, and that the ``init_args`` values are valid
arguments to instantiate it. The parsed config keeps the ``class_path`` and
``init_args`` entries. :meth:`instantiate <.ArgumentParser.instantiate>` gives a
config object with all nested subclasses instantiated.

Besides using a class as type hint in a signature, parsers can be built with
:meth:`add_class_arguments <.ArgumentParser.add_class_arguments>` and
:meth:`add_subclass_arguments <.ArgumentParser.add_subclass_arguments>`. These
accept a ``skip`` argument to exclude parameters inside subclasses, given as a
relative destination key, i.e. ``param.init_args.subparam``. A single argument
can also be added with a class as type, i.e. ``parser.add_argument("--module",
type=ModuleBase)``.

A simple example, with a top-level class whose parameter expects an injected
class instance, uses a config file ``config.yaml`` as:

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

Here the ``class_path`` points to the same class used as the type. A subclass of
``Calendar``, with more init parameters, would work as well.

Using :meth:`add_subclass_arguments <.ArgumentParser.add_subclass_arguments>`
instead of :meth:`add_class_arguments <.ArgumentParser.add_class_arguments>`
would also accept subclasses of ``MyClass``, and the config would be:

.. code-block:: yaml

    myclass:
      class_path: my_module.MyClass
      init_args:
        calendar:
          class_path: calendar.TextCalendar
          init_args:
            firstweekday: 1

.. note::

    A parameter of type ``Any``, ``object``, or ``Untyped``, accepts a dict with
    ``class_path`` and ``init_args``, and the class is parsed and instantiated.

    This instantiation is deprecated. From v5.0.0 the subclass spec is kept as
    is, so that the code receiving it decides whether to instantiate it. Set
    ``instantiate_subclass_spec_in_any=False`` in :func:`.set_parsing_settings`
    to get this behavior now and silence the deprecation warning. Setting it to
    ``True`` keeps the instantiation, but is discouraged, since it means that a
    config can instantiate any class, which is a security risk.

    A value that looks like a subclass spec, i.e. has a ``class_path``, but
    can't be parsed as one, e.g. because the class fails to import, is by
    default left unchanged and a debug message is logged. Set
    ``validate_subclass_spec_in_any=True`` in :func:`.set_parsing_settings` to
    make parsing fail instead. Besides ``Any``, ``object`` and
    ``Unvalidated<...>``, this also applies to dicts that don't validate their
    values, e.g. ``dict[str, Any]``. For dicts the spec is only validated, since
    the value stays a dict. This matters for unions such as ``Union[SomeClass,
    dict[str, Any]]``, where a spec rejected by the class member would otherwise
    be silently swallowed by the dict member.

.. note::

    ``class_path`` also accepts a function whose return type is a class. The
    accepted ``init_args`` are then the parameters of that function.

.. note::

    Abstract classes, i.e. classes that have abstract methods, are not accepted
    as ``class_path``, since they can't be instantiated. For the same reason
    they are not among the known subclasses shown in the help.


.. _untrusted-configs:

Untrusted configs
-----------------

Resolving a ``class_path`` imports the named module and instantiates the named
class with the given ``init_args``, so a config decides what code runs. When the
configs come from a trusted source, this is not a concern. When they don't, e.g.
a config uploaded by a user of a service, an import path denylist limits what a
config can reach.

Import paths that come from a value, i.e. a ``class_path``, a ``Callable``, a
``type[...]`` or a ``types.ModuleType`` given in a config file, the command line
or an environment variable, are checked against a denylist before the import
happens. Paths that come from code, e.g. type annotations and defaults, are
never checked. jsonargparse denies a set of paths by default, mostly standard
library modules that give arbitrary code execution, e.g. ``os``, ``subprocess``,
``pickle`` and ``importlib``. Two settings adjust the list:

.. testsetup:: import_paths

    saved_import_path_settings = dict(_common.parsing_settings)

.. testcode:: import_paths

    from jsonargparse import set_parsing_settings

    set_parsing_settings(
        import_path_denylist=["mypackage._internal"],
        import_path_allowlist=["functools.partial"],
    )

An entry denies or allows a dot import path and everything under it, so ``os``
also denies ``os.system``. The most specific entry decides, which is why
``functools.partial`` above is allowed even though ``functools`` is denied by
default. An entry given in both lists is allowed, so naming a default entry in
``import_path_allowlist`` is how to stop denying it. The one exception is
``jsonargparse`` itself, which is denied by default and not accepted in
``import_path_allowlist``, since a value that names it would be able to call
:func:`.set_parsing_settings` and thus change the policy that is checking it.

An object is denied by where it is defined, not only by the path used to reach
it. Modules commonly import others, e.g. ``import os``, so without this
``some.module.os.system`` would give the same object as the denied
``os.system``. This second check can only happen once the object is resolved, so
it prevents the object from being used, unlike the check on the given path,
which prevents the import from happening at all. An object that has no defining
path of its own is denied by the callable it reaches, i.e. the bound function
for a ``functools.partial`` and the defining class for an instance, e.g.
``builtins.help`` is an instance of the ``_sitebuiltins._Helper`` class.

Entries given are added to the ones denied by default, they don't replace them.
For configs that are entirely untrusted, prefer denying everything and allowing
only what the application expects. The ``*`` entry is only accepted in
``import_path_denylist``:

.. testcode:: import_paths

    set_parsing_settings(
        import_path_denylist=["*"],
        import_path_allowlist=["mypackage.tools"],
    )

.. testcleanup:: import_paths

    _common.parsing_settings.clear()
    _common.parsing_settings.update(saved_import_path_settings)

The denylist is not the only thing that limits what a config can reach. Type
hints do as well, since a ``class_path`` is only accepted where the annotation
allows one, and must name a subclass of the annotated type. The exceptions are
``Any`` and ``object``, which accept a subclass spec of any class, see
:ref:`sub-classes`. Setting ``instantiate_subclass_spec_in_any=False``, which is
the default from v5.0.0, keeps these values as plain dicts, so nothing is
imported or instantiated and the code that receives the dict decides what to do
with it. The denylist still applies when ``validate_subclass_spec_in_any=True``,
since validating a spec requires importing the class it names.

.. note::

    A denylist is a mitigation, not a sandbox. A large enough set of installed
    dependencies is likely to contain something that reaches a denied capability
    without naming a denied path, e.g. a class that runs a command given to it.
    Only ``*`` plus a narrow allowlist gives a bound on what a config can
    import.

.. note::

    The ``omegaconf`` parser modes, see :ref:`omegaconf-interpolation`, give a
    config access to OmegaConf's resolvers, which the import path denylist does
    not check. The built-in ``oc.env`` resolver reads environment variables, so
    a value of ``${oc.env:AWS_SECRET_ACCESS_KEY}`` puts that variable's value
    into the config, and the resolvers that the application registers are
    equally reachable. Avoid these parser modes for untrusted configs.

.. note::

    Until v5.0.0 a denied import path only gives a deprecation warning and the
    import proceeds, so that existing configs don't break. Giving a value to
    ``import_path_denylist`` or ``import_path_allowlist``, an empty list
    included, makes denied import paths fail instead. From v5.0.0 they always
    fail.


.. _sub-config-files:

Sub-config files
----------------

Instead of writing a subclass spec inline, a path to a config file that holds it
can be given. This splits a large config into smaller reusable files. It
requires the argument to be added with ``sub_configs=True``, which is the
default in :func:`.auto_cli` and is accepted by :meth:`add_argument
<.ArgumentParser.add_argument>` and the ``add_*_arguments`` methods.

This also works for the items of a list of classes and for the values of a dict
of classes, useful when each component has its own config file. For example,
take the following classes:

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
directory of that file, so a group of config files can be moved around without
being modified. :meth:`save <.ArgumentParser.save>` with ``multifile=True``
writes each sub-config back to its own file, keeping the original structure.

:ref:`subclasses-disabled` types also accept a sub-config file, whose content is
the fields of the type, without ``class_path`` and ``init_args``. This only
applies when the type is not added as an argument group, i.e. when it is part of
a larger type, e.g. ``Optional[SomeDataclass]`` or ``list[SomeDataclass]``. When
added as a group, the group's own config argument accepts the path, e.g.
``--data=data.yaml``, independent of ``sub_configs``.


.. _instance-factories:

Instance factories
------------------

As mentioned in :ref:`dependency-injection`, callables that return instances of
classes, called instance factories, are the other way of doing dependency
injection. They are useful for classes that need parameters which are only
available after injection. In this case :meth:`instantiate
<.ArgumentParser.instantiate>` gives a partial function, which takes those
parameters and returns the instance. There are two options, ``Callable`` and
``Protocol``. For the ``Callable`` option, take the classes:

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

A parser and its behavior could be:

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

    When the ``Callable`` returns a class, the ``class_path`` can be given as
    just the class name, if the class was imported before parsing, see
    :ref:`sub-classes-command-line`.

When the same type above is used in a signature, a lambda can set the default:

.. testcode:: callable

    class Model:
        def __init__(
            self,
            optimizer: Callable[[Iterable], Optimizer] = lambda p: SGD(p, lr=0.05),
        ):
            self.optimizer = optimizer

A parser then gives:

.. code-block::

    >>> parser.add_class_arguments(Model, 'model')
    >>> cfg = parser.get_defaults()
    >>> cfg.model.optimizer
    Namespace(class_path='__main__.SGD', init_args=Namespace(lr=0.05))
    >>> init = parser.instantiate(cfg)
    >>> optimizer = init.model.optimizer([1, 2, 3])
    >>> optimizer.params, optimizer.lr
    ([1, 2, 3], 0.05)

See :ref:`ast-resolver` for the limitations of lambda defaults in signatures. A
lambda default given to :meth:`add_argument <.ActionsContainer.add_argument>`
does not work, since there is no AST resolving. Use a dict with ``class_path``
and ``init_args`` as default instead.

Several arguments after injection work the same way, e.g. ``Callable[[Iterable,
Iterable], Type]`` for two ``Iterable`` arguments, and ``Callable[[], Type]``
for none.

``Callable`` has an important limitation: its parameters are positional and
unnamed. The second option, a callable ``Protocol``, avoids this. For the same
example:

.. testcode:: callable

    class OptimizerFactory(Protocol):
        def __call__(self, params: Iterable) -> Optimizer: ...

A parser using it behaves as:

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

The difference is that ``init.optimizer()`` can now be called with keyword
arguments, i.e. ``params=[6, 5]``.

.. _sub-classes-command-line:

Command line
------------

The help does not show the parameters of a class, since these depend on the
chosen subclass. A help option that takes an import path gives them. For a
parser defined as:

.. testcode::

    from calendar import Calendar
    from jsonargparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("--calendar", type=Calendar)

the help of a subclass is printed with:

.. code-block:: bash

    python tool.py --calendar.help calendar.TextCalendar

A subclass can be given through several command line arguments:

.. code-block:: bash

    python tool.py \
      --calendar.class_path calendar.TextCalendar \
      --calendar.init_args.firstweekday 1

For convenience, ``.class_path`` and ``.init_args`` can be omitted, and the
subclass can be named instead of giving its full import path:

.. code-block:: bash

    python tool.py --calendar TextCalendar --calendar.firstweekday 1

Naming the subclass works for subclasses in modules that were imported before
parsing. Abstract classes and private classes (module or name starting with
``'_'``) are not considered. The general help, ``python tool.py --help``, lists
all the subclasses that can be given by name.

When the base class is not abstract, the ``class_path`` can be omitted, by
giving directly ``init_args``, for example:

.. code-block:: bash

    python tool.py --calendar.firstweekday 2

would implicitly use ``calendar.Calendar`` as the class path.


Default values
--------------

A parameter that has a class as type can also have a default value. Take care
with this: it can be considered bad practice and is best avoided in most cases.
The problem is that classes are normally mutable, so depending on how the value
is used, the default instance in the signature can end up modified. That is not
what a default value should be, and leads to bugs that are hard to debug.

Since there are legitimate use cases, class instances in defaults are supported
with a particular behavior. An example is:

.. testcode:: instance_default

    class MyClass:
        def __init__(
            self,
            calendar: Calendar = Calendar(firstweekday=1),
        ):
            self.calendar = calendar

Adding this class to a parser works without issues. In limited cases the
:ref:`ast-resolver` figures out how the original default was instantiated, and
then the parse methods give a dict with ``class_path`` and ``init_args`` instead
of the instance. :meth:`instantiate <.ArgumentParser.instantiate>` creates a new
instance, which avoids the mutability problem.

When the :ref:`ast-resolver` does not support the case, or the source code is
not available, the second approach is to instantiate the default with the
:func:`.lazy_instance` function:

.. testcode:: instance_default

    from jsonargparse.typing import lazy_instance


    class MyClass:
        def __init__(
            self,
            calendar: Calendar = lazy_instance(Calendar, firstweekday=1),
        ):
            self.calendar = calendar

The parsed default is then again a dict with ``class_path`` and ``init_args``,
avoiding the mutability risk.

:func:`.lazy_instance` is somewhat discouraged. Delaying the initialization of
instances in a way that works in general is hard, and the current implementation
is known to have some problems. Consider using :ref:`instance-factories`
instead.

.. note::

    For some classes and functions the import path can't be determined from the
    object alone. Using one of these as a default fails when serializing, since
    what gets saved in the config file is the import path. To solve this, give
    the module from which the object can be imported to
    :func:`.register_unresolvable_import_paths`.


.. _subclasses-disabled:

Class types with subclasses disabled
------------------------------------

Sometimes a class is used as a type hint with no intention of accepting
subclasses. For the parser this means that a subclass is not allowed, and that
serializing stores the init arguments directly, without ``class_path`` and
``init_args``. The standard Python way to express this is the :func:`.final`
decorator. For example:

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

Sometimes subclasses are not intended but the :func:`.final` decorator is not
used. For example, requiring a ``class_path`` for a simple ``x, y`` coordinates
dataclass would be needlessly cumbersome. For this reason jsonargparse early on
gave the same behavior to pure ``dataclasses`` (not mixed with normal classes),
attrs' ``define``, pydantic's ``dataclass`` and pydantic's ``BaseModel``. These
classes do technically support subclassing, so subclass support can be enabled
as described below. It is disabled by default to avoid breaking changes.

A type with subclasses disabled is added as an argument group when it is the
entire type of an argument, so each of its init args becomes an individual
argument, e.g. ``--data.number``. This does not happen when the type is part of
a larger type, e.g. ``Optional[FinalClass]`` or ``list[FinalClass]``, since then
a single argument must accept the whole value. Either way the accepted values
are the same. A subclass spec is accepted, but only with the ``class_path`` of
the type itself, i.e. ``--data={"class_path": "FinalClass", "init_args":
{"number": 8}}``. The ``class_path`` of a subclass is not accepted, unless
subclass support is enabled for the type as described next.

Abstract dataclass-like types are an exception. A class that has abstract
methods or that inherits from ``abc.ABC`` is not meant to be instantiated from
its own fields, so for these types subclass support is enabled by default, i.e.
only the ``class_path`` of an implementation is accepted.


.. _enable-disable-subclasses:

Enable/disable subclasses
-------------------------

The ``subclasses_disabled`` and ``subclasses_enabled`` parameters of
:func:`.set_parsing_settings` control which class types support subclasses.

``subclasses_disabled`` accepts a list of types and functions. A given type and
its descendants have subclass support disabled. A function receives a type and
returns ``True`` if subclasses should be disabled for it.

``subclasses_enabled`` accepts a list of types and function names. A given type
and its descendants have subclass support enabled, and take precedence over
``subclasses_disabled``. A function name must be one previously registered in
``subclasses_disabled``, and the effect is to unregister it. The disabling
functions registered by default are ``is_pure_dataclass``,
``is_pydantic_model``, ``is_attrs_class`` and ``is_final_class``. These are not
applied to abstract classes, see above.

Since ``subclasses_enabled`` takes precedence, subclass support can be kept
disabled for dataclasses but enabled for a specific one:

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

To enable subclass support for all pydantic models:

.. testcode:: enable_disable_subclasses

    set_parsing_settings(subclasses_enabled=["is_pydantic_model"])

To enable it for all dataclasses but disable it for a specific one:

.. testcode:: enable_disable_subclasses

    set_parsing_settings(
        subclasses_enabled=["is_pure_dataclass"],
        subclasses_disabled=[DataClassBaseType],
    )

.. note::

    Enabling subclass support for types is experimental. The interface and
    behavior are expected to be stable, but fundamental issues may still require
    design changes, which could break things in future releases.


.. _argument-linking:

Argument linking
================

Some use cases add arguments from several classes, where a parameter gets its
value computed from other arguments. The :meth:`link_arguments
<.ArgumentParser.link_arguments>` parser method does this.

There are two types of links, ``apply_on='parse'`` and
``apply_on='instantiate'``. As the names say, the first are applied by the parse
methods and the second by :meth:`instantiate <.ArgumentParser.instantiate>`.

Applied on parse
----------------

For parse links, the source keys can be single arguments or nested groups, and
the target key must be a single argument. Keys can be inside the ``init_args``
of a subclass. The compute function takes as many positional arguments as there
are sources, and returns a value of a type compatible with the target. For
example:

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

Only ``data.batch_size`` is given, on the command line or in a config file, and
its value is propagated to ``model.batch_size``.

An example with the target inside a subclass:

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

The link is applied to the ``logger`` parameter when it is a single subclass,
and to all elements when it is a list of subclasses. If a subclass does not have
the targeted ``init_args`` parameter, the link is ignored.

Applied on instantiate
----------------------

For instantiate links, the sources can be class groups (added with
:meth:`add_class_arguments <.ArgumentParser.add_class_arguments>`) or subclass
arguments (see :ref:`sub-classes`). The source key is the instantiated object
itself or one of its attributes. The target key must be a single argument, and
can be inside the ``init_args`` of a subclass. :meth:`instantiate
<.ArgumentParser.instantiate>` determines the instantiation order from the
links, so all instantiate links together must form a directed acyclic graph. For
example:

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

This link makes :meth:`instantiate <.ArgumentParser.instantiate>` build ``Data``
first, and then use its ``num_classes`` attribute to build ``Model``.


.. _omegaconf-interpolation:

OmegaConf variable interpolation
================================

One reason to add a parser mode (see :ref:`custom-loaders`) is to support
variable interpolation. Any library can be used for this. Without writing a
loader, an ``omegaconf`` parser mode is available out of the box when the
omegaconf package is installed.

For example, a YAML file:

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

It is parsed as:

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

    ``parser_mode="omegaconf"`` supports `OmegaConf's resolvers
    <https://omegaconf.readthedocs.io/en/latest/usage.html#variable-interpolation>`__
    within a single YAML file. Interpolation across several YAML files, or in a
    single command line argument, is not possible.

Experimental ``omegaconf+`` mode
--------------------------------

The experimental ``omegaconf+`` parser mode removes the limitations above.
Instead of resolving each YAML config on its own, resolving happens once at the
end of parsing. As a result, in nested subconfigs, node references must be
relative or absolute at the parser level. Alternatively,
``set_parsing_settings(omegaconf_absolute_to_relative_paths=True)`` converts
absolute paths to relative ones while parsing, though this does not work in
every case.

Depending on community feedback, this mode may become the default ``omegaconf``
mode eventually. That would be a breaking change, since absolute node references
would no longer work in nested subconfigs.


.. _environment-variables:

Environment variables
=====================

Parsers can also get values from environment variables. The name of a variable
is ``[PREFIX_][LEV__]*OPT``: all upper case, a prefix, an underscore, and then
the argument name with each dot replaced by two underscores. The prefix is
``env_prefix``, or the ``prog`` without extension when ``env_prefix`` is unset,
or none when it is ``False``. For the parser from :ref:`nested-namespaces`, the
shell variables are:

.. code-block:: bash

    export APP_LEV1__OPT1='from env 1'
    export APP_LEV1__OPT2='from env 2'

The parser then uses these variables, unless the command line overrides them:

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

Note the ``default_env=True`` given to the parser. By default :meth:`parse_args
<.ArgumentParser.parse_args>` does not parse environment variables. If
``default_env`` is left unset, they can also be enabled by setting
``JSONARGPARSE_DEFAULT_ENV=true`` in the shell.

The :meth:`parse_env <.ArgumentParser.parse_env>` method parses only environment
variables, useful when there is no command line call.

If the parser has an ``action="config"`` argument, its environment variable is
parsed before all the others.


.. _sub-commands:

Subcommands
===========

Subcommands are a modular way of defining parsers, like `subcommands
<https://docs.python.org/3/library/argparse.html#subcommands>`__ in argparse. In
jsonargparse they behave somewhat differently, see :ref:`argparse-deviations`.

Add subcommands to a parser with :meth:`add_subcommands
<.ArgumentParser.add_subcommands>`, and then add an existing parser as a
subcommand with :meth:`add_subcommand <.ActionSubCommands.add_subcommand>`. In
the parsed namespace, the chosen subcommand is under the ``subcommand`` key (or
the key given by ``dest``), and its arguments are nested under a key with the
subcommand's name. For example:

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

Some parsing examples:

.. doctest::

    >>> parser.parse_args(["subcomm1", "--op1", "val1"])  # doctest: +IGNORE_RESULT
    Namespace(op0=None, subcommand='subcomm1', subcomm1=Namespace(op1='val1'))
    >>> parser.parse_args(["--op0", "val0", "subcomm2", "--op2", "val2"])  # doctest: +IGNORE_RESULT
    Namespace(op0='val0', subcommand='subcomm2', subcomm2=Namespace(op2='val2'))

Config files can also be parsed, with :meth:`parse_path
<.ArgumentParser.parse_path>` or :meth:`parse_string
<.ArgumentParser.parse_string>`. The config file does not need to give a value
for ``subcommand``. For the parser above, a valid YAML is:

.. code-block:: yaml

    # File: example.yaml
    op0: val0
    subcomm1:
      op1: val1

Environment variables work like for :class:`.ActionParser`. For the parser
above, the variables of ``subcomm1`` have the prefix ``APP_SUBCOMM1_`` and those
of ``subcomm2`` the prefix ``APP_SUBCOMM2_``. The subcommand itself is chosen
with ``APP_SUBCOMMAND``.

Several levels of subcommands are possible, with one requirement: they must be
added in order of level. That is, first call :meth:`add_subcommands
<.ArgumentParser.add_subcommands>` and :meth:`add_subcommand
<.ActionSubCommands.add_subcommand>` for the first level, only then for the
second level, and so on.


.. _json-schemas:

JSON Schemas
============

The :class:`.ActionJsonSchema` class parses and validates values with a JSON
Schema. It requires the `jsonschema <https://pypi.org/project/jsonschema/>`__
package, which is not part of the minimal install. Install jsonargparse with the
``jsonschema`` extra, see :ref:`installation`.

See the `JSON Schema documentation
<https://python-jsonschema.readthedocs.io/>`__ to learn how to write a schema.
jsonargparse currently uses ``Draft7Validator``. An example:

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

The value can also be a path to a JSON/YAML file, which is loaded and validated
against the schema. Default values defined in the schema initialize the config
values that are not given. In the ``help`` string, ``"%s"`` is replaced by the
schema.


.. _jsonnet-files:

Jsonnet files
=============

Jsonnet support requires the `jsonschema
<https://pypi.org/project/jsonschema/>`__ and `jsonnet
<https://pypi.org/project/jsonnet/>`__ packages, which are not part of the
minimal install. Install jsonargparse with the ``jsonnet`` extra, see
:ref:`installation`.

By default an :class:`.ArgumentParser` parses config files as YAML. With
``parser_mode='jsonnet'``, :meth:`parse_args <.ArgumentParser.parse_args>`,
:meth:`parse_path <.ArgumentParser.parse_path>` and :meth:`parse_string
<.ArgumentParser.parse_string>` expect Jsonnet instead:

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

Jsonnet files are often parametrized and need external variables. For these,
instead of changing the parser mode away from ``yaml``, use the
:class:`.ActionJsonnet` class. It defines an argument that takes a Jsonnet
string or a path to a Jsonnet file, plus another argument as the source of the
external variables, given as a path to, or a string with, a JSON dictionary:

.. testcode:: jsonnet

    from jsonargparse import ArgumentParser, ActionJsonnet

    parser = ArgumentParser()
    parser.add_argument("--in_ext_vars", type=dict)
    parser.add_argument("--in_jsonnet", action=ActionJsonnet(ext_vars="in_ext_vars"))

For example, if a Jsonnet file required some external variable ``param``, then
the Jsonnet and the external variable could be given as:

.. testcode:: jsonnet

    cfg = parser.parse_args(["--in_ext_vars", '{"param": 123}', "--in_jsonnet", "example.jsonnet"])

The external variables argument must come before the Jsonnet path, so that the
dictionary already exists when the Jsonnet is parsed.

:class:`.ActionJsonnet` also accepts a JSON Schema, and then validates the
Jsonnet against it right after parsing.


.. _parser-arguments:

Parsers as arguments
====================

An existing parser, needed standalone somewhere in the code, can be reused to
parse an inner node of a larger parser. The :class:`.ActionParser` class defines
such an argument:

.. testcode::

    from jsonargparse import ArgumentParser, ActionParser

    inner_parser = ArgumentParser(prog="app1")
    inner_parser.add_argument("--op1")
    ...
    outer_parser = ArgumentParser(prog="app2")
    outer_parser.add_argument("--inner.node", title="Inner node title", action=ActionParser(parser=inner_parser))

In a config file, the value of the node can be the node itself, or the path to a
file that is loaded and parsed with the inner parser. Parsing a complete config
file with ``action="config"`` naturally parses the inner nodes correctly.

Note the ``title`` given when adding ``inner_parser``. In the help, added
parsers are shown as independent groups starting with that ``title``. A
``description`` can also be given.

For environment variables, the prefix of the outer parser is used for the leaf
nodes of the inner parser. In the example above, ``inner_parser`` on its own
checks ``APP1_OP1`` to populate option ``op1``, while ``outer_parser`` checks
``APP2_INNER__NODE__OP1`` to populate ``inner.node.op1``.

An important detail is that the parsers given to :class:`.ActionParser` are
modified internally. So to use a parser both standalone and as an inner node,
write a function that creates it, and call that function in each place, so that
each one gets its own instance.


.. _tab-completion:
.. _completion-scripts:

Completion scripts
==================

From a parser, jsonargparse can generate artifacts that describe what the parser
accepts, so that other tools can validate and complete configs and command
lines. The supported completion types are:

- ``jsonschema``: a JSON Schema that describes the config files that the parser
  accepts. Always available.
- ``shtab-*``: a completion script for a given shell, e.g. ``shtab-bash``.
  Available when the `shtab <https://pypi.org/project/shtab/>`__ package is
  installed.

Both are generated with the :meth:`.ArgumentParser.get_completion_script`
method, or from the command line, see :ref:`print-completion-argument`.

Completion at runtime in the shell, which jsonargparse supports through the
`argcomplete <https://pypi.org/project/argcomplete/>`__ package, is covered
further down in :ref:`argcomplete`. It involves no generated artifact.


.. _print-completion-argument:

The --print_completion argument
-------------------------------

To enable generation of completion scripts via the command line, use
:func:`.set_parsing_settings` with ``add_print_completion_argument=True``. This
adds a ``--print_completion`` argument to top-level parsers (not subparsers),
which accepts the completion types listed above.

.. testcode::

    from jsonargparse import set_parsing_settings

    set_parsing_settings(add_print_completion_argument=True)

Without changing Python code, the argument is also added by setting the
environment variable ``JSONARGPARSE_ADD_PRINT_COMPLETION_ARGUMENT=true``.


jsonschema
----------

The ``jsonschema`` completion type gives a `JSON Schema
<https://json-schema.org/>`__ (draft 2020-12) that describes the config files
accepted by the parser.

.. testcode::

    parser = ArgumentParser(prog="example")
    parser.add_argument("--bool", type=bool)

    schema = parser.get_completion_script("jsonschema")
    # schema now contains the JSON schema

The equivalent from the command line is:

.. code-block:: bash

    $ example.py --print_completion=jsonschema > schema.json

This schema is useful as a machine-readable interface for tools. For example:

- IDE/editor assistance (autocompletion, hints, and inline validation).
- Config contract checks in CI pipelines.
- Generating documentation from parser structure.

To get validation and autocompletion for a config file in an editor such as
`Visual Studio Code
<https://code.visualstudio.com/docs/languages/json#_json-schemas-and-settings>`__,
the config can point to the generated schema with a ``$schema`` key:

.. code-block:: json

    {
      "$schema": "./schema.json",
      "bool": true
    }

The key is accepted in any config that a parser loads, :ref:`sub-config-files`
included, and it is removed before parsing, so it never becomes part of the
parsed namespace. Accordingly, every object in the schema that describes a
config accepts the key.

The schema is derived from the same information that the ``--help`` output is
based on, so it includes:

- The structure of nested keys, i.e. argument groups and subclasses-disabled
  types become objects, and which of their keys are required.
- The accepted types, including unions, literals, enums, containers and the
  restrictions of types such as :class:`.PositiveInt` and :class:`.Email`. For
  the plain argparse actions, which have no type hint, this is what the action
  gives, e.g. a boolean for ``store_true``, an integer for ``count``, the
  possible values for ``store_const`` and an array for ``append``.
- The defaults of the arguments. Three kinds are left out: the required ones,
  the ones whose default is ``argparse.SUPPRESS``, since not giving those leaves
  no key, and the unset ones, see :ref:`unset-values`. Without
  ``unset_sentinel``, a ``None`` default counts as unset, so ``null`` is never
  described as a default. With it, an explicit ``default=None`` is described, as
  long as the type accepts ``null``.
- Descriptions taken from the docstrings of the classes and functions that the
  arguments come from, or from the ``help`` given to ``add_argument``.
- For subclass types, one entry per known subclass, each with a ``class_path``
  fixed to that subclass and an ``init_args`` object describing the accepted
  init parameters of that specific class.
- For parsers with subcommands, one object per subcommand and a ``subcommand``
  key. This key is optional, since a config that has a single subcommand block
  implies it, and when a config has several blocks the subcommand can be given
  as a command line argument.

Subclasses and types that are used in more than one place are added once to
``$defs`` and referenced with ``$ref``, which also makes recursive types work.

The schema is meant to accept what the parser accepts, but for subclass types it
is stricter. A string is accepted, since it can be a class path or a path to a
sub-config file. An object is only accepted for the known subclasses, i.e. one
with ``class_path``, ``init_args`` (required only for the subclasses that have a
required init parameter) and ``dict_kwargs``. Accepting any ``class_path`` would
keep tools from suggesting the known subclasses and from pointing out a class
path that has a typo or is not the accepted import path, and its ``init_args``
would go undescribed. Any ``class_path`` is accepted only when a type has no
known subclass, and then its ``init_args`` are not described.

A union that has a subtype accepting anything, i.e. ``Any`` or an unvalidated
type, is kept as ``{"anyOf": [..., {}]}`` instead of the equivalent ``{}``, so
that tools still have the other subschemas to describe and complete against. The
exception is when another subtype restricts the keys of an object, e.g. a
subclass, dataclass or typed dict. Then the subschemas that accept any object,
i.e. those from ``Any``, ``dict`` and unvalidated types, are removed. This makes
the schema stricter than the parser, but in exchange mistakes in the keys are
pointed out instead of going unnoticed.

.. note::

    The subclasses of a type that the schema includes are the ones known to
    Python when the schema is generated, i.e. only those whose modules happen to
    have been imported.

.. note::

    The ``jsonschema`` completion type is experimental. The details of the
    generated schema might change in non-major releases.


shtab
-----

The ``shtab-*`` completion types give a shell completion script, using
``shtab-`` followed by the shell name, e.g. ``shtab-bash`` or ``shtab-zsh``.

For ``shtab`` there is no need to set ``complete``/``choices`` on the parser
actions, or to call `shtab.add_argument_to
<https://docs.iterative.ai/shtab/ref/#add_argument_to>`__. The only requirement
is to install shtab, directly or with the ``shtab`` extra, see
:ref:`installation`.

.. testcode::

    parser = ArgumentParser(prog="example")
    parser.add_argument("--bool", type=bool)

    script = parser.get_completion_script("shtab-bash", preambles=[])
    # script now contains the bash completion script

.. warning::

    After calling :meth:`.get_completion_script` for an ``shtab-*`` completion
    type, the parser instance is invalidated and cannot be used for parsing
    arguments.

From the command line, for example in Linux to enable bash completions for all
users, as root:

.. code-block:: bash

    # example.py --print_completion=shtab-bash > /etc/bash_completion.d/example

Without installing, a script can be tested by sourcing or evaluating it:

.. code-block:: bash

    $ eval "$(example.py --print_completion=shtab-bash)"

Completion behavior
^^^^^^^^^^^^^^^^^^^

The scripts complete when there are choices, and also print guidance for the
user. Take for example the parser:

.. testsetup:: tab_completion

    sys.argv = [""]

.. testcode:: tab_completion

    #!/usr/bin/env python3

    from jsonargparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("--bool", type=bool | None)

    parser.parse_args()

The completion prints the type of the argument, how many options match, and then
the matching choices. If only one option matches, the value is completed without
printing guidance. For example:

.. code-block:: bash

    $ example.py --bool <TAB><TAB>
    Expected type: bool | None; 3/3 matched choices
    true  false  null
    $ example.py --bool f<TAB>
    $ example.py --bool false

For subclass types, the import paths of the known subclasses are completed, both
for the option that selects the class and for the ``--*.help`` option. The
``init_args`` of the known subclasses are completed too, with guidance saying
which subclasses accept each one. For example:

.. code-block:: bash

    $ example.py --cls <TAB><TAB>
    Expected type: BaseClass; 3/3 matched choices
    some.module.BaseClass     other.module.SubclassA
    other.module.SubclassB
    $ example.py --cls other.module.SubclassA --cls.<TAB><TAB>
    --cls.param1    --cls.param2
    $ example.py --cls other.module.SubclassA --cls.param2 <TAB><TAB>
    Expected type: int; Accepted by subclasses: SubclassA

Analogously, for subclasses-disabled types and ``TypedDict``, the fields or keys
are completed, as well as the values that they accept, e.g.:

.. code-block:: bash

    $ example.py --data.<TAB><TAB>
    --data.verbose    --data.mode
    $ example.py --data.verbose <TAB><TAB>
    Expected type: bool; 2/2 matched choices
    true  false

.. _argcomplete:

argcomplete
-----------

For ``argcomplete`` there is no need to implement completer functions or to call
`argcomplete.autocomplete
<https://kislyuk.github.io/argcomplete/#argcomplete.autocomplete>`__, since
:meth:`parse_args <.ArgumentParser.parse_args>` does it automatically. The only
requirement is to install argcomplete, directly or with the ``argcomplete``
extra, see :ref:`installation`.

The shell completion can be enabled `globally
<https://kislyuk.github.io/argcomplete/#global-completion>`__ for all
argcomplete compatible tools or for each `individual
<https://kislyuk.github.io/argcomplete/#synopsis>`__ tool.

Using the same ``bool`` example, activate completion and use it as follows:

.. code-block:: bash

    $ eval "$(register-python-argcomplete example.py)"

    $ example.py --bool <TAB><TAB>
    false  null   true
    $ example.py --bool f<TAB>
    $ example.py --bool false


.. _argparse-deviations:

Deviations from argparse
========================

To keep a high level of compatibility with argparse, the argparse tests from the
Python standard library are run against jsonargparse. Some are skipped because
they cover intentional deviations, are not relevant for jsonargparse, or are
still under investigation and may be enabled later. Which tests to skip is
configured in the ``argparse_tests_generate.py`` file.

The following sections describe the main intentional deviations from argparse.
In addition, deprecated features in argparse are not supported.

Subcommands
-----------

In argparse, a parser with subcommands merges the main parser and subparser
options into a single flat namespace. Since jsonargparse supports nested
namespaces, subcommand options are deliberately placed in their own
subnamespace, which is clearer and more convenient.

In argparse, ``add_subparsers`` needs the ``dest`` parameter for the name of the
chosen subcommand to appear in the namespace. In jsonargparse it is there by
default, without any extra parameter.

To promote modularity, jsonargparse subparsers are created independently, just
like the main parser, and then added as a subcommand. This makes it possible to
write functions that return a subparser, usable both standalone and as a
subcommand. In argparse, subparsers are tightly coupled to the main parser and
can't be defined independently. To avoid confusion with argparse, the method
names for adding subcommands are intentionally different.

To migrate from argparse to jsonargparse, instead of:

.. testcode::

    import argparse

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    subparser1 = subparsers.add_parser("foo")
    subparser1.add_argument("--key")
    ...

the code becomes:

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

Argparse has a ``parse_known_args`` method, which parses leniently by ignoring
unrecognized arguments. jsonargparse is designed for complex cases: several
subcommands, many arguments derived from signatures, class instantiation and
config files. Ignoring unrecognized arguments would make errors, such as a typo
in a config file, harder to notice. For this reason ``parse_known_args`` is
intentionally not supported.

User defined types
------------------

In argparse, the ``type`` parameter of an argument can be a user-defined
function or class. A function is supported in jsonargparse, with the extra
requirement that it must be idempotent, i.e. applying it twice or more does not
change the value. For example:

.. testcode::

    # either int larger than zero or 'off' string
    def int_or_off(x):
        return x if x == "off" else int(x)


    parser.add_argument("--int_or_off", type=int_or_off)

A class as the type conflicts with the signature and type hint support that is
central to jsonargparse, so it does not work the same way as in argparse. The
recommended alternative is to implement a custom type, see :ref:`custom-types`.


.. _logging:

Troubleshooting and logging
===========================

When a parse method fails, by default it prints a short message and exits with a
non-zero code. During development this is not enough information to find the
root of the problem. Setting the ``JSONARGPARSE_DEBUG`` environment variable to
``true`` changes this, without touching the source code: an
:class:`.ArgumentError` is raised and the full stack trace is printed.

The parsers log some basic events, though this is disabled by default. To enable
it, set the ``logger`` argument when creating an :class:`.ArgumentParser`. The
intended use is to give the logger object that the whole application uses. For
convenience, ``logger`` can also be ``True`` to enable a default logger, a
string with the name of the logger, or a dictionary with the name and the level,
e.g. ``{"name": "myapp", "level": "ERROR"}``.
