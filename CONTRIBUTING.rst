Contributing
============

Contributions to jsonargparse are very welcome. There are multiple ways for
people to help and contribute, among them:

- Star ⭐ the GitHub project `<https://github.com/mauvilsa/jsonargparse/>`__.
- `Sponsor 🩷 <https://github.com/sponsors/mauvilsa>`__ its maintenance and
  development.
- Spread the word in your community about the features you like from
  jsonargparse.
- Help others to learn how to use jsonargparse by creating tutorials, such as
  blog posts and videos.
- Become active in existing GitHub issues and pull requests.
- Create `issues <https://github.com/mauvilsa/jsonargparse/issues>`__ for
  reporting bugs and proposing improvements.
- Create `pull requests <https://github.com/mauvilsa/jsonargparse/pulls>`__ with
  documentation improvements, bug fixes or new features.

.. note::

    While creating an issue before submitting a pull request is not mandatory,
    it might be helpful. Issues allow for discussion and feedback before
    significant development effort is invested. However, in some cases, code
    changes can better illustrate a proposal, making it more effective to submit
    a pull request directly. In such cases please avoid opening a largely
    redundant issue.

Development environment
-----------------------

If you intend to work with the source code, note that this project does not
include any ``requirements.txt`` file. This is by intention. To make it very
clear what are the requirements for different use cases, all the requirements of
the project are stored in the file ``pyproject.toml``. The basic runtime
requirements are defined in ``dependencies``. Requirements for optional features
are stored in ``[project.optional-dependencies]``. Also in the same section
there are requirements for testing, development and documentation building:
``test``, ``dev`` and ``doc``.

The recommended way to work with the source code is the following. First clone
the repository, then create a virtual environment, activate it and finally
install the development requirements. More precisely the steps are:

.. code-block:: bash

    git clone https://github.com/mauvilsa/jsonargparse.git
    cd jsonargparse
    python -m venv venv
    . venv/bin/activate

The crucial step is installing the requirements which would be done by running:

.. code-block:: bash

    pip install -e ".[dev]"

pre-commit
----------

Please also install the `pre-commit <https://pre-commit.com/>`__ git hooks so
that unit tests and code checks are automatically run locally. This is done as
follows:

.. code-block:: bash

    pre-commit install

.. note::

    ``.pre-commit-config.yaml`` is configured to run the hooks using Python
    3.12. Ensure you have Python 3.12 installed and available in your
    environment for ``pre-commit`` to function correctly. For development, other
    Python versions will work, but for convenience, Python 3.12 is recommended.

The ``pre-push`` stage runs several hooks, including tests, doctests, mypy, and
coverage. These hooks are designed to inform developers of issues that must be
resolved before a pull request can be merged. Note that these hooks may take
some time to complete. If you wish to push without running these hooks, use the
command ``git push --no-verify``.

Formatting of the code is done automatically by pre-commit. If some pre-commit
hooks fail and you decide to skip them, formatting will be automatically applied
by a GitHub action in pull requests.

Documentation
-------------

To build the documentation run:

.. code-block:: bash

    sphinx-build sphinx sphinx/_build sphinx/*.rst

To view the built documentation, open the file ``sphinx/_build/index.html`` in a
browser.

Code conventions
----------------

**Public vs. private naming**

Most module filenames start with ``_``, meaning they are private implementation
details. For objects within modules, the ``_`` prefix indicates the object is
only used within that same module. An object without a ``_`` prefix may be
imported by other modules but that does not make it public — it is simply
internal to the package. The only truly public objects are those listed in
``jsonargparse.__all__`` and ``jsonargparse.typing.__all__``.

**Type annotations and docstrings**

New source code should be fully type annotated. Docstrings should follow `Google
style
<https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings>`__.

Tests
-----

Running the unit tests can be done either using `pytest
<https://docs.pytest.org/>`__ or `tox
<https://tox.readthedocs.io/en/stable/>`__. Also pre-commit runs some additional
tests.

.. code-block:: bash

    tox                                      # Run tests using tox on available python versions
    pytest                                   # Run tests using pytest on the python of the environment
    pre-commit run -a --hook-stage pre-push  # Run pre-push git hooks (tests, doctests, mypy, coverage)

Tests can be run in any environment without the source code. Before v4.47.0, the
tests were included in the main package. Since v4.47.0, they are provided in a
separate package. Prefer installing the tests package with the same version as
the main package. For example, for v4.47.0 run:

.. code-block:: bash

    pip install jsonargparse_tests==4.47.0
    python -m jsonargparse_tests

All contributed features and bug fixes must include tests. For bug fixes, ensure
the test fails without the code fix. Almost always tests should exercise only
the public API. Testing internal functions directly is rarely justified and
should be avoided. For tests involving signatures, define the classes and
functions used at the global module scope. Jsonargparse is not intended to
support dynamically defined classes and functions, so there is no value in
testing such cases.

For maintainable tests:

- Prefer ``pytest.mark.parametrize`` when the same test logic is exercised with
  different inputs.
- Use fixtures for repeated setup and shared test resources, especially when
  multiple tests need the same files, parser configuration, or environment.
- Avoid pushing trivial one-line setup into fixtures when it makes the test
  harder to read.
- Keep setup separate from assertions so each test clearly shows the behavior
  being verified.
- The pytest output must be clean. If a test causes log output, the logs must
  be captured and asserted using the ``logger`` fixture and ``capture_logs``
  context manager from ``conftest.py``.


Coverage
--------

For a nice html test coverage report, run:

.. code-block:: bash

    pytest --cov --cov-report=html

Then open the file ``htmlcov/index.html`` in a browser.

To get a full coverage report, you need to install all supported python
versions, and then:

.. code-block:: bash

    rm -fr jsonargparse_tests/.coverage jsonargparse_tests/htmlcov
    tox -- --cov=../jsonargparse --cov-append
    cd jsonargparse_tests
    coverage html

Then open the file ``jsonargparse_tests/htmlcov/index.html`` in a browser.

Pull requests
-------------

When creating a pull request, it is recommended that you create a specific
branch in your fork for the changes you want to contribute, instead of using the
``main`` branch.

The required tasks to do for a pull request, are listed in
`PULL_REQUEST_TEMPLATE.md
<https://github.com/mauvilsa/jsonargparse/blob/main/.github/PULL_REQUEST_TEMPLATE.md>`__.

One of the tasks is adding a changelog entry. For this, note that this project
uses semantic versioning. Depending on whether the contribution is a bug fix or
a new feature, the changelog entry would go in a patch or minor release. The
changelog section for the next release does not have a definite date, for
example:

.. code-block::

    v4.28.0 (unreleased)
    --------------------

    Added
    ^^^^^
    -

If no such section exists, just add it with "(unreleased)" instead of a date.
Have a look at previous releases to decide under which subsection the new entry
should go. If you are unsure, ask in the pull request.

Please don't open pull requests with breaking changes unless this has been
discussed and agreed upon in an issue.

Contributions using coding agents are welcome. However, any agent-generated
code must be fully understood by the submitter and must make sense and follow
these contributing guidelines. Always ask the agent to read and follow these
guidelines. Also ask to read ``.github/PULL_REQUEST_TEMPLATE.md`` so that the
tasks before submitting are covered.
