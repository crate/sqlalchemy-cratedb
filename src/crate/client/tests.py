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

import sys
import unittest
import doctest
from pprint import pprint
import logging

from crate.testing.settings import crate_host, docs_path
from crate.client import connect
from sqlalchemy_cratedb import SA_VERSION, SA_1_4

makeSuite = unittest.TestLoader().loadTestsFromTestCase

log = logging.getLogger()
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
log.addHandler(ch)


def cprint(s):
    if isinstance(s, bytes):
        s = s.decode('utf-8')
    print(s)


crate_layer = None


def setUpCrateLayerBaseline(test):
    test.globs['crate_host'] = crate_host
    test.globs['pprint'] = pprint
    test.globs['print'] = cprint

    with connect(crate_host) as conn:
        cursor = conn.cursor()

        with open(docs_path('testing/testdata/mappings/locations.sql')) as s:
            stmt = s.read()
            cursor.execute(stmt)
            stmt = ("select count(*) from information_schema.tables "
                    "where table_name = 'locations'")
            cursor.execute(stmt)
            assert cursor.fetchall()[0][0] == 1

        data_path = docs_path('testing/testdata/data/test_a.json')
        # load testing data into crate
        cursor.execute("copy locations from ?", (data_path,))
        # refresh location table so imported data is visible immediately
        cursor.execute("refresh table locations")
        # create blob table
        cursor.execute("create blob table myfiles clustered into 1 shards " +
                       "with (number_of_replicas=0)")

        # create users
        cursor.execute("CREATE USER me WITH (password = 'my_secret_pw')")
        cursor.execute("CREATE USER trusted_me")

        cursor.close()


def setUpCrateLayerSqlAlchemy(test):
    """
    Setup tables and views needed for SQLAlchemy tests.
    """
    setUpCrateLayerBaseline(test)

    ddl_statements = [
        """
        CREATE TABLE characters (
            id STRING PRIMARY KEY,
            name STRING,
            quote STRING,
            details OBJECT,
            more_details ARRAY(OBJECT),
            INDEX name_ft USING fulltext(name) WITH (analyzer = 'english'),
            INDEX quote_ft USING fulltext(quote) WITH (analyzer = 'english')
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
        )"""
    ]
    _execute_statements(ddl_statements, on_error="raise")


def tearDownDropEntitiesBaseline(test):
    """
    Drop all tables, views, and users created by `setUpWithCrateLayer*`.
    """
    ddl_statements = [
        "DROP TABLE locations",
        "DROP BLOB TABLE myfiles",
        "DROP USER me",
        "DROP USER trusted_me",
    ]
    _execute_statements(ddl_statements)


def tearDownDropEntitiesSqlAlchemy(test):
    """
    Drop all tables, views, and users created by `setUpWithCrateLayer*`.
    """
    tearDownDropEntitiesBaseline(test)
    ddl_statements = [
        "DROP TABLE characters",
        "DROP VIEW characters_view",
        "DROP TABLE cities",
    ]
    _execute_statements(ddl_statements)


def _execute_statements(statements, on_error="ignore"):
    with connect(crate_host) as conn:
        cursor = conn.cursor()
        for stmt in statements:
            _execute_statement(cursor, stmt, on_error=on_error)
        cursor.close()


def _execute_statement(cursor, stmt, on_error="ignore"):
    try:
        cursor.execute(stmt)
    except Exception:  # pragma: no cover
        # FIXME: Why does this croak on statements like ``DROP TABLE cities``?
        # Note: When needing to debug the test environment, you may want to
        #       enable this logger statement.
        # log.exception("Executing SQL statement failed")
        if on_error == "ignore":
            pass
        elif on_error == "raise":
            raise


def test_suite():
    suite = unittest.TestSuite()
    flags = (doctest.NORMALIZE_WHITESPACE | doctest.ELLIPSIS)

    sqlalchemy_integration_tests = [
        'docs/by-example/sqlalchemy/getting-started.rst',
        'docs/by-example/sqlalchemy/crud.rst',
        'docs/by-example/sqlalchemy/working-with-types.rst',
        'docs/by-example/sqlalchemy/advanced-querying.rst',
        'docs/by-example/sqlalchemy/inspection-reflection.rst',
    ]

    # Don't run DataFrame integration tests on SQLAlchemy 1.3 and Python 3.7.
    skip_dataframe = SA_VERSION < SA_1_4 or sys.version_info < (3, 8)
    if not skip_dataframe:
        sqlalchemy_integration_tests += [
            'docs/by-example/sqlalchemy/dataframe.rst',
        ]

    s = doctest.DocFileSuite(
        *sqlalchemy_integration_tests,
        module_relative=False,
        setUp=setUpCrateLayerSqlAlchemy,
        tearDown=tearDownDropEntitiesSqlAlchemy,
        optionflags=flags,
        encoding='utf-8'
    )
    suite.addTest(s)

    return suite
