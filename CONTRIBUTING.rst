.. _contributing:

Contributing
============

Contributions to jsonargparse are very welcome. There are many ways to help,
among them:

- Star ⭐ the GitHub project `<https://github.com/mauvilsa/jsonargparse/>`__.
- `Sponsor 🩷 <https://github.com/sponsors/mauvilsa>`__ its maintenance and
  development.
- Spread the word in your community about the features you like from
  jsonargparse.
- Help others learn how to use jsonargparse by creating tutorials, such as blog
  posts and videos. If you do, let us know so that it can be added to
  :ref:`talks-and-articles`.
- Become active in existing GitHub issues and pull requests.
- Create `issues <https://github.com/mauvilsa/jsonargparse/issues>`__ to report
  bugs and propose improvements.
- Create `pull requests <https://github.com/mauvilsa/jsonargparse/pulls>`__ with
  documentation improvements, bug fixes or new features.

.. note::

    Creating an issue before submitting a pull request is not mandatory, but it
    can be helpful, since it allows for discussion and feedback before
    significant effort is invested. In some cases, though, code changes
    illustrate a proposal better, so submitting a pull request directly is more
    effective. In such cases please avoid opening a largely redundant issue.

Development environment
-----------------------

All requirements of the project are defined in ``pyproject.toml``. The basic
runtime requirements are in ``dependencies``. Requirements for optional
features, as well as for testing, development and documentation building
(``test``, ``dev`` and ``doc``), are in ``[project.optional-dependencies]``.

The recommended way to work with the source code is to clone the repository,
create a virtual environment, activate it, and install the development
requirements:

.. code-block:: bash

    git clone https://github.com/mauvilsa/jsonargparse.git
    cd jsonargparse
    python -m venv venv
    . venv/bin/activate
    pip install -e ".[dev,all]"

pre-commit
----------

Please also install the `pre-commit <https://pre-commit.com/>`__ git hooks, so
that unit tests and code checks run automatically on your machine:

.. code-block:: bash

    pre-commit install

.. note::

    ``.pre-commit-config.yaml`` is configured to run the hooks using Python
    3.12, so make sure that this version is installed and available. Other
    Python versions work for development, but 3.12 is recommended for
    convenience.

The ``pre-push`` stage runs several hooks, including tests, doctests, mypy and
coverage. They inform developers of issues that must be resolved before a pull
request can be merged, and can take some time to complete. To push without
running them, use ``git push --no-verify``. Formatting of the code is applied
automatically by pre-commit. Even when pushing with ``--no-verify``, please make
sure that the formatting has been applied.

Documentation
-------------

To build the documentation run:

.. code-block:: bash

    sphinx-build sphinx sphinx/_build sphinx/*.rst

Then open the file ``sphinx/_build/index.html`` in a browser.

Code conventions
----------------

**Public vs. private naming**

Most module filenames start with ``_``, meaning they are private implementation
details. For objects within modules, the ``_`` prefix indicates the object is
only used within that same module. An object without a ``_`` prefix may be
imported by other modules, but that does not make it public — it is simply
internal to the package. The only truly public objects are those listed in
``jsonargparse.__all__`` and ``jsonargparse.typing.__all__``.

**Type annotations and docstrings**

New source code should be fully type annotated. Docstrings should follow `Google
style
<https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings>`__.

Tests
-----

The unit tests can be run with `pytest <https://docs.pytest.org/>`__ or `tox
<https://tox.readthedocs.io/en/stable/>`__. Pre-commit runs some additional
tests.

.. code-block:: bash

    tox                                      # Run tests using tox on available python versions
    pytest                                   # Run tests using pytest on the python of the environment
    pre-commit run -a --hook-stage pre-push  # Run pre-push git hooks (tests, doctests, mypy, coverage)

The tests can also be run in any environment without the source code. Since
v4.47.0 they are provided in a separate package, whereas before they were
included in the main package. Prefer installing the tests package with the same
version as the main package, for example:

.. code-block:: bash

    pip install jsonargparse_tests==4.47.0
    python -m jsonargparse_tests

All contributed features and bug fixes must include tests. For bug fixes, ensure
that the test fails without the code fix. Tests should almost always exercise
only the public API; testing internal functions directly is rarely justified and
should be avoided. For tests involving signatures, define the classes and
functions at the global module scope. Jsonargparse is not intended to support
dynamically defined classes and functions, so there is no value in testing such
cases.

For maintainable tests:

- Prefer ``pytest.mark.parametrize`` when the same test logic is exercised with
  different inputs.
- Use fixtures for repeated setup and shared test resources, especially when
  multiple tests need the same files, parser configuration, or environment.
- Avoid pushing trivial one-line setup into fixtures when it makes the test
  harder to read.
- Keep setup separate from assertions, so that each test clearly shows the
  behavior being verified.
- Keep the pytest output clean. If a test causes log output, the logs must be
  captured and minimally asserted using the ``logger`` fixture and
  ``capture_logs`` context manager from ``conftest.py``.


Coverage
--------

Coverage is required to be 100% in ``jsonargparse/*`` files, with realistic
tests and without unwarranted ``# pragma: no cover``. This ensures that all
existing code is actually needed.

For a nice html coverage report, run:

.. code-block:: bash

    pytest --cov --cov-report=html

Then open the file ``htmlcov/index.html`` in a browser.

A full coverage report requires all supported Python versions to be installed,
and then:

.. code-block:: bash

    rm -fr jsonargparse_tests/.coverage jsonargparse_tests/htmlcov
    tox --parallel -- --cov=../jsonargparse --cov-append
    cd jsonargparse_tests
    coverage html

Then open the file ``jsonargparse_tests/htmlcov/index.html`` in a browser.

Pull requests
-------------

For the changes you want to contribute, it is recommended to create a specific
branch in your fork, instead of using the ``main`` branch.

The tasks required for a pull request are listed in `PULL_REQUEST_TEMPLATE.md
<https://github.com/mauvilsa/jsonargparse/blob/main/.github/PULL_REQUEST_TEMPLATE.md>`__.

One of the tasks is adding a changelog entry. This project uses semantic
versioning, so the entry goes in a patch release for a bug fix, or in a minor
release for a new feature. The changelog section for the next release does not
have a definite date, for example:

.. code-block::

    v4.28.0 (unreleased)
    --------------------

    Added
    ^^^^^
    -

If no such section exists, just add it with "(unreleased)" instead of a date.
Have a look at previous releases to decide under which subsection the new entry
should go. Entries must describe changes with respect to the previous release,
not with respect to unreleased commits.

Please don't open pull requests with breaking changes, unless this has been
discussed and agreed upon in an issue.

Contributions using coding agents are welcome. However, any agent-generated code
must be fully understood by the submitter, must make sense, and must follow
these contributing guidelines. Always ask the agent to read and follow this
document, and also ``.github/PULL_REQUEST_TEMPLATE.md``, so that the tasks
required before submitting are covered.
