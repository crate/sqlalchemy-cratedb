# CrateDB Python developer guide

## Setup

To start things off, bootstrap the sandbox environment:

    git clone https://github.com/crate-workbench/sqlalchemy-cratedb
    cd sqlalchemy-cratedb
    source bootstrap.sh

This command should automatically install all prerequisites for the
development sandbox and drop you into the virtualenv, ready for invoking
further commands.

## Running Tests

Verify code by running all linters and software tests:

    docker compose -f tests/docker-compose.yml up
    poe check

Run specific tests:

    pytest -k SqlAlchemyCompilerTest
    pytest -k test_score

    # Integration tests, written as doctests.
    python -m unittest -vvv tests/integration.py

Format code:

    poe format


## Preparing a release

In the release branch:

-   Update `__version__` in `src/crate/client/__init__.py`
-   Add a section for the new version in the `CHANGES.txt` file
-   Commit your changes with a message like \"prepare release x.y.z\"
-   Push to origin/\<release_branch\>
-   Create a tag by running `./devtools/create_tag.sh`. This will
    trigger a GitHub action which releases the new version to PyPi.

On branch `main`:

-   Update the release notes to reflect the release


## Writing documentation

The docs live under the `docs` directory.

The docs are written with [ReStructuredText] and Markdown,
and will be processed with [Sphinx].

Build the docs by running:

    ./bin/sphinx

The output can then be found in the `out/html` directory.

The docs are automatically built from Git by [Read the Docs]. There is
nothing special you need to do to get the live docs to update.


[Read the Docs]: http://readthedocs.org
[ReStructuredText]: https://docutils.sourceforge.net/rst.html
[Sphinx]: https://sphinx-doc.org/
