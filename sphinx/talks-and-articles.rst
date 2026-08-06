:orphan:

.. _talks-and-articles:

Talks and articles
==================

Presentations, videos, blog posts and example projects that show jsonargparse
in action. They are a good complement to this documentation, since they explain
the *why* behind the features and walk through complete use cases.

Note that these materials are snapshots in time. The library evolves, so some
details might differ from the current release. Always refer to the
documentation of the version you are using.

If you have created something that would fit in this list, contributions are
very welcome, see :ref:`contributing`.


From API client to CLI
----------------------

*Series of blog posts by Mauricio Villegas, 2026*

A series that starts from a plain Python class wrapping an HTTP API and, step by
step, turns it into a command line tool that is installable, configurable and
tab completable. Not a single argument parser is written along the way, and the
class stays free of any CLI concern, so it remains equally usable from a
notebook or a web service.

- Example repository: https://github.com/mauvilsa/blog-earthquake-cli


Part 1: From API client to CLI, without writing a parser
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*2026-08-03*

A client for the USGS earthquake catalog becomes a full CLI with a single
:func:`.auto_cli` call. Shows how the signatures, type hints and docstrings that
the class already has are enough to get subcommands, help, validated choices,
nested dataclass options and config file support.

- Post: https://dev.to/mauvilsa/from-api-client-to-cli-without-writing-a-parser-3h01


Part 2: A CLI that works from anywhere
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*2026-08-10*

The CLI from part 1 only runs from its own directory. Packaging it with a
``pyproject.toml`` entry point makes it a command available anywhere, and
``default_config_files`` gives it settings that follow it around, layered from
system-wide to user to project, with the help showing which defaults a config
changed.

- Post: https://dev.to/mauvilsa/a-cli-that-works-from-anywhere-5hf0


Part 3: Tab completion without writing a completion script
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*2026-08-20*

A CLI knows what its valid values are, so users should not have to memorize them
or dig through the help. One setting,
:func:`.set_parsing_settings` with ``add_print_completion_argument``, adds a
``--print_completion`` option that emits completion scripts for bash, zsh, fish
and tcsh, with completions that are aware of subcommands, literal choices, paths
and nested dataclass fields.

- Post: https://dev.to/mauvilsa/tab-completion-without-writing-a-completion-script-4nab


Low effort configurable python: type hints and dependency injection
-------------------------------------------------------------------

*Presentation by Mauricio Villegas at PyBerlin 48, 2024-07-24*

Why making a project configurable matters, and why it does not have to be
daunting. Explains how pytorch-lightning's ``LightningCLI`` was designed so that
developers get configurability with minimal effort, and how to apply the same
dependency injection ideas to your own projects with jsonargparse.

- Meetup event: https://www.meetup.com/pyberlin/events/301394594/
- Slides: https://drive.google.com/file/d/1Cf9Om5c33_4ZNeNfJv3axVlAJwLwTzYu/view


jsonargparse - Say goodbye to configuration hassles
---------------------------------------------------

*Presentation by Marianne Stecklina at PyCon DE & PyData Berlin 2022,
2022-04-12*

A tour of the configuration troubles that appear as a project grows:
hard-coded parameters, the need for a CLI, juggling several config files and
dependencies between parameters. Shows how jsonargparse builds on top of
argparse to deal with them, with a runnable example project to follow along.

- Talk page: https://2022.pycon.de/program/XK73C3/
- Presentation video: https://youtu.be/2gDf2S0nHKg
- Slides: https://speakerdeck.com/stecklin/jsonargparse-say-goodbye-to-configuration-hassles
- Example repository: https://github.com/stecklin/pycon22-jsonargparse
