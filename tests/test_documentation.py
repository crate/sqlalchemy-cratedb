# -*- coding: utf-8; -*-
#
# Licensed to CRATE Technology GmbH ("Crate") under one or more contributor
# license agreements.  See the NOTICE file distributed with this work for
# additional information regarding copyright ownership.  Crate licenses
# this file to you under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.  You may
# obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
# License for the specific language governing permissions and limitations
# under the License.
#
# However, if you have executed another commercial license agreement
# with Crate these terms will supersede the license and you may use the
# software solely pursuant to the terms of the relevant commercial agreement.

from __future__ import absolute_import

import doctest
import logging
import os
import unittest
from pprint import pprint

import pytest
from crate.client import connect

from sqlalchemy_cratedb.sa_version import SA_2_0, SA_VERSION

log = logging.getLogger()
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
log.addHandler(ch)


def cprint(s):
    if isinstance(s, bytes):
        s = s.decode("utf-8")
    print(s)  # noqa: T201


def docs_path(*parts):
    return os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), *parts))


def provision_database(crate_host):
    drop_tables(crate_host)

    with connect(crate_host) as conn:
        cursor = conn.cursor()

        with open(docs_path("tests/assets/locations.sql")) as s:
            stmt = s.read()
            cursor.execute(stmt)
            stmt = "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'locations'"
            cursor.execute(stmt)
            assert cursor.fetchall()[0][0] == 1

        # `/assets` is mounted into the CrateDB container, see `tests/conftest.py`.
        data_path = "/assets/locations.jsonl"

        cursor.execute("COPY locations FROM ?", (data_path,))
        cursor.execute("REFRESH TABLE locations")
        cursor.execute(
            "CREATE BLOB TABLE myfiles CLUSTERED INTO 1 SHARDS " + "WITH (number_of_replicas=0)"
        )
        cursor.execute("CREATE USER me WITH (password = 'my_secret_pw')")
        cursor.execute("CREATE USER trusted_me")

        cursor.close()

    ddl_statements = [
        """
        CREATE TABLE characters (
            id STRING PRIMARY KEY,
            name STRING,
            quote STRING,
            details OBJECT,
            more_details ARRAY(OBJECT),
            INDEX name_ft USING FULLTEXT(name) WITH (analyzer = 'english'),
            INDEX quote_ft USING FULLTEXT(quote) WITH (analyzer = 'english')
            )""",
        """
        CREATE VIEW characters_view
            AS SELECT * FROM characters
        """,
        """
        CREATE TABLE cities (
            name STRING PRIMARY KEY,
            coordinate GEO_POINT,
            area GEO_SHAPE
        )""",
        """
        CREATE TABLE search (
            name STRING PRIMARY KEY,
            text STRING,
            embedding FLOAT_VECTOR(3)
        )""",
    ]
    _execute_statements(crate_host, ddl_statements)


def drop_tables(crate_host):
    """
    Drop all tables, views, and users created by the test suite.
    """
    ddl_statements = [
        "DROP TABLE IF EXISTS archived_tasks",
        "DROP TABLE IF EXISTS characters",
        "DROP TABLE IF EXISTS cities",
        "DROP TABLE IF EXISTS foobar",
        "DROP TABLE IF EXISTS locations",
        "DROP BLOB TABLE IF EXISTS myfiles",
        "DROP TABLE IF EXISTS search",
        'DROP TABLE IF EXISTS "test-testdrive"',
        "DROP TABLE IF EXISTS todos",
        'DROP TABLE IF EXISTS "user"',
        "DROP VIEW IF EXISTS characters_view",
        "DROP USER IF EXISTS me",
        "DROP USER IF EXISTS trusted_me",
    ]
    _execute_statements(crate_host, ddl_statements)


def _execute_statements(crate_host, statements, on_error="raise"):
    with connect(crate_host) as conn:
        cursor = conn.cursor()
        for stmt in statements:
            _execute_statement(cursor, stmt, on_error=on_error)
        cursor.close()


def _execute_statement(cursor, stmt, on_error="raise"):
    if on_error not in ["ignore", "raise"]:
        raise ValueError(f"Invalid value for `on_error` argument: {on_error}")
    try:
        cursor.execute(stmt)
    except Exception:  # pragma: no cover
        # FIXME: Why does this croak on statements like ``DROP TABLE cities``?
        # Note: When needing to debug the test environment, you may want to
        #       enable this logger statement.
        # log.exception("Executing SQL statement failed")  # noqa: ERA001
        if on_error == "ignore":
            pass
        elif on_error == "raise":
            raise


def setUp(test):
    provision_database(test.globs["crate_host"])

    test.globs["pprint"] = pprint
    test.globs["print"] = cprint


def tearDown(test):
    # The CrateDB instance is shared with the rest of the test suite.
    drop_tables(test.globs["crate_host"])


DOCTEST_FILES = [
    "docs/getting-started.rst",
    "docs/crud.rst",
    "docs/working-with-types.rst",
    "docs/advanced-querying.rst",
    pytest.param(
        "docs/dataframe.rst",
        marks=pytest.mark.skipif(
            SA_VERSION < SA_2_0,
            reason="Don't run DataFrame integration tests on SQLAlchemy 1.4 and earlier",
        ),
    ),
    "docs/inspection-reflection.rst",
]


@pytest.mark.parametrize("filename", DOCTEST_FILES)
def test_documentation(crate_host, filename):
    """
    Run the doctests of a documentation page against the session's CrateDB instance.
    """
    suite = doctest.DocFileSuite(
        docs_path(filename),
        module_relative=False,
        setUp=setUp,
        tearDown=tearDown,
        globs={"crate_host": crate_host},
        optionflags=doctest.NORMALIZE_WHITESPACE | doctest.ELLIPSIS,
        encoding="utf-8",
    )
    result = unittest.TestResult()
    suite.run(result)
    problems = result.failures + result.errors
    if problems:
        pytest.fail("\n".join(traceback for _, traceback in problems), pytrace=False)
