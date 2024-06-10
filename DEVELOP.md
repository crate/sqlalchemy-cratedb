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

On branch `main`:

-   Add a section for the new version in the `CHANGES.md` file
-   Commit your changes with a message like \"Release x.y.z\"
-   Push to origin/\<release_branch\>
-   Create a tag, and push to remote.
    ```shell
    git tag v0.0.1
    git push --tags
    ```
-   Build package, and upload to PyPI.
    ```shell
    poe release
    ```

On GitHub:

-   Designate a new release on GitHub, copying in the relevant section
    from the CHANGELOG.
    https://github.com/crate-workbench/sqlalchemy-cratedb/releases


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
