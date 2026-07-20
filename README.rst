.. image:: https://readthedocs.org/projects/jsonargparse/badge/?version=stable
    :target: https://readthedocs.org/projects/jsonargparse/
.. image:: https://github.com/mauvilsa/jsonargparse/actions/workflows/tests.yaml/badge.svg
    :target: https://github.com/mauvilsa/jsonargparse/actions/workflows/tests.yaml
.. image:: https://codecov.io/gh/mauvilsa/jsonargparse/branch/main/graph/badge.svg
    :target: https://codecov.io/gh/mauvilsa/jsonargparse
.. image:: https://sonarcloud.io/api/project_badges/measure?project=mauvilsa_jsonargparse&metric=alert_status
    :target: https://sonarcloud.io/dashboard?id=mauvilsa_jsonargparse
.. image:: https://badge.fury.io/py/jsonargparse.svg
    :target: https://badge.fury.io/py/jsonargparse


jsonargparse
============

Docs: https://jsonargparse.readthedocs.io/ | Source: https://github.com/mauvilsa/jsonargparse/

``jsonargparse`` is a library for creating command-line interfaces (CLIs) and
making Python apps easily configurable. It is a well-maintained project with
frequent releases, adhering to high standards of development: semantic
versioning, deprecation periods, changelog, automated testing, and full test
coverage.

Although ``jsonargparse`` might not be widely recognized yet, it already boasts
a `substantial user base
<https://github.com/mauvilsa/jsonargparse/network/dependents>`__. Most notably,
it serves as the framework behind pytorch-lightning's `LightningCLI
<https://lightning.ai/docs/pytorch/stable/cli/lightning_cli.html>`__.

Teaser examples
---------------

CLI with minimal boilerplate:

.. code-block:: python

    from jsonargparse import auto_cli

    def main_function(...):  # your main parameters with type hints here
        ...  # your main code here

    if __name__ == "__main__":
        auto_cli(main_function)  # parses arguments and runs main_function

Minimal boilerplate but manually parsing:

.. code-block:: python

    from jsonargparse import auto_parser

    parser = auto_parser(main_function)
    cfg = parser.parse_args()
    ...

Powerful argparse-like low level parsers:

.. code-block:: python

    from jsonargparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("--config", action="config")  # support config files
    parser.add_argument("--opt", type=int | Literal["off"])  # complex arguments via type hints
    parser.add_function_arguments(main_function, "function")  # add function parameters
    parser.add_class_arguments(SomeClass, "class")  # add class parameters
    ...
    cfg = parser.parse_args()
    init = parser.instantiate(cfg)
    ...


Features
--------

``jsonargparse`` is user-friendly and encourages the development of **clean,
high-quality code**. It encompasses numerous powerful features, some unique to
``jsonargparse``, while also combining advantages found in similar packages:

- **Automatic** creation of CLIs, like `Fire
  <https://pypi.org/project/fire/>`__, `Typer
  <https://pypi.org/project/typer/>`__, `Clize
  <https://pypi.org/project/clize/>`__ and `Tyro
  <https://pypi.org/project/tyro/>`__.

- Use **type hints** for argument validation, like `Typer
  <https://pypi.org/project/typer/>`__, `Tap
  <https://pypi.org/project/typed-argument-parser/>`__ and `Tyro
  <https://pypi.org/project/tyro/>`__.

- Use of **docstrings** for automatic generation of help, like `Tap
  <https://pypi.org/project/typed-argument-parser/>`__, `Tyro
  <https://pypi.org/project/tyro/>`__ and `SimpleParsing
  <https://pypi.org/project/simple-parsing/>`__.

- Parse from **configuration files** and **environment variables**, like
  `OmegaConf <https://pypi.org/project/omegaconf/>`__, `dynaconf
  <https://pypi.org/project/dynaconf/>`__, `confuse
  <https://pypi.org/project/confuse/>`__ and `configargparse
  <https://pypi.org/project/ConfigArgParse/>`__.

- **Dataclasses** support, like `SimpleParsing
  <https://pypi.org/project/simple-parsing/>`__ and `Tyro
  <https://pypi.org/project/tyro/>`__.


Other notable features include:

- **Extensive type hint support:** nested types (union, optional), containers
  (list, dict, etc.), protocols, user-defined generics, restricted types (regex,
  numbers), paths, URLs, types from stubs (``*.pyi``), future annotations (PEP
  `563 <https://peps.python.org/pep-0563/>`__), and backports (PEP `604
  <https://peps.python.org/pep-0604>`__).

- **Keyword arguments introspection:** resolving of parameters used via
  ``**kwargs``.

- **Dependency injection:** support types that expect a class instance and
  callables that return a class instance.

- **Structured configs:** parse config files with more understandable non-flat
  hierarchies.

- **Config file formats:** `json <https://www.json.org/>`__, `yaml
  <https://yaml.org/>`__, `toml <https://toml.io/>`__, `jsonnet
  <https://jsonnet.org/>`__ and extensible to more formats.

- **Relative paths:** within config files and parsing of config paths referenced
  inside other configs.

- **Argument linking:** directing parsed values to multiple parameters,
  preventing unnecessary interpolation in configs.

- **Variable interpolation:** powered by `OmegaConf
  <https://omegaconf.readthedocs.io/en/latest/usage.html#variable-interpolation>`__.

- **Tab completion:** powered by `shtab
  <https://pypi.org/project/shtab/>`__ or `argcomplete
  <https://pypi.org/project/argcomplete/>`__.


Design principles
-----------------

- **Non-intrusive/decoupled:**

  There is no requirement for unrelated modifications throughout a codebase,
  maintaining the `separation of concerns principle
  <https://en.wikipedia.org/wiki/Separation_of_concerns>`__. In simpler terms,
  changes should make sense even without the CLI. No need to inherit from a
  special class, add decorators, or use CLI-specific type hints.

- **Minimal boilerplate:**

  A recommended practice is to write code with function/class parameters having
  meaningful names, accurate type hints, and descriptive docstrings. Reuse these
  wherever they appear to automatically generate the CLI, following the `don't
  repeat yourself principle
  <https://en.wikipedia.org/wiki/Don%27t_repeat_yourself>`__. A notable
  advantage is that when parameters are added or types changed, the CLI will
  remain synchronized, avoiding the need to update the CLI's implementation.

- **Dependency injection:**

  Using as type hint a class or a callable that instantiates a class, a practice
  known as `dependency injection
  <https://en.wikipedia.org/wiki/Dependency_injection>`__, is a sound design
  pattern for developing loosely coupled and highly configurable software. Such
  type hints should be supported with minimal restrictions.


.. _installation:

Installation
============

You can install using `pip <https://pypi.org/project/jsonargparse/>`__ as:

.. code-block:: bash

    pip install jsonargparse

By default, the only dependency installed with ``jsonargparse`` is `PyYAML
<https://pypi.org/project/PyYAML/>`__. However, several optional features can be
enabled by specifying one or more of the following extras (optional
dependencies): ``signatures``, ``jsonschema``, ``jsonnet``, ``urls``,
``fsspec``, ``toml``, ``ruamel``, ``omegaconf``, ``shtab``, and ``argcomplete``.
Additionally, the ``all`` extras can be used to enable all optional features
(excluding tab completion ones). To install ``jsonargparse`` with extras, use
the following syntax:

.. code-block:: bash

    pip install "jsonargparse[signatures,urls]"  # Enable signatures and URLs features
    pip install "jsonargparse[all]"              # Enable all optional features

To install the latest development version, use the following command:

.. code-block:: bash

    pip install "jsonargparse[signatures] @ https://github.com/mauvilsa/jsonargparse/zipball/main"
