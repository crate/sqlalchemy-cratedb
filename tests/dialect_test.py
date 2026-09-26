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

from datetime import datetime
from unittest import TestCase, skipIf
from unittest.mock import MagicMock, patch

import sqlalchemy as sa
from crate.client.cursor import Cursor
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from sqlalchemy_cratedb import ObjectType
from sqlalchemy_cratedb.sa_version import SA_1_4, SA_2_0, SA_VERSION

try:
    from sqlalchemy.orm import declarative_base
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.testing import eq_, in_, is_true

FakeCursor = MagicMock(name="FakeCursor", spec=Cursor)


@patch("crate.client.connection.Cursor", FakeCursor)
class SqlAlchemyDialectTest(TestCase):
    def execute_wrapper(self, query, *args, **kwargs):
        self.executed_statement = query
        return self.fake_cursor

    def setUp(self):
        self.fake_cursor = MagicMock(name="fake_cursor")
        FakeCursor.return_value = self.fake_cursor

        self.engine = sa.create_engine("crate://")

        self.executed_statement = None

        self.connection = self.engine.connect()

        self.fake_cursor.execute = self.execute_wrapper

        self.base = declarative_base()

        class Character(self.base):
            __tablename__ = "characters"

            name = sa.Column(sa.String, primary_key=True)
            age = sa.Column(sa.Integer, primary_key=True)
            obj = sa.Column(ObjectType)
            ts = sa.Column(sa.DateTime, onupdate=datetime.utcnow)

        self.session = Session(bind=self.engine)

    def init_mock(self, return_value=None):
        self.fake_cursor.rowcount = 1
        self.fake_cursor.description = (("foo", None, None, None, None, None, None),)
        self.fake_cursor.fetchall = MagicMock(return_value=return_value)

    def test_primary_keys_2_3_0(self):
        insp = inspect(self.session.bind)
        self.engine.dialect.server_version_info = (2, 3, 0)

        self.fake_cursor.rowcount = 3
        self.fake_cursor.description = (("foo", None, None, None, None, None, None),)
        self.fake_cursor.fetchall = MagicMock(return_value=[["id"], ["id2"], ["id3"]])

        eq_(insp.get_pk_constraint("characters")["constrained_columns"], ["id", "id2", "id3"])
        self.fake_cursor.fetchall.assert_called_once_with()
        in_("information_schema.key_column_usage", self.executed_statement)
        in_("table_catalog = ?", self.executed_statement)

    def test_primary_keys_3_0_0(self):
        insp = inspect(self.session.bind)
        self.engine.dialect.server_version_info = (3, 0, 0)

        self.fake_cursor.rowcount = 3
        self.fake_cursor.description = (("foo", None, None, None, None, None, None),)
        self.fake_cursor.fetchall = MagicMock(return_value=[["id"], ["id2"], ["id3"]])

        eq_(insp.get_pk_constraint("characters")["constrained_columns"], ["id", "id2", "id3"])
        self.fake_cursor.fetchall.assert_called_once_with()
        in_("information_schema.key_column_usage", self.executed_statement)
        in_("table_schema = ?", self.executed_statement)

    def test_get_table_names(self):
        self.fake_cursor.rowcount = 1
        self.fake_cursor.description = (("foo", None, None, None, None, None, None),)
        self.fake_cursor.fetchall = MagicMock(return_value=[["t1"], ["t2"]])

        insp = inspect(self.session.bind)
        self.engine.dialect.server_version_info = (2, 0, 0)
        eq_(insp.get_table_names(schema="doc"), ["t1", "t2"])
        in_(
            "WHERE table_schema = ? AND table_type = 'BASE TABLE' ORDER BY", self.executed_statement
        )

    def test_get_view_names(self):
        self.fake_cursor.rowcount = 1
        self.fake_cursor.description = (("foo", None, None, None, None, None, None),)
        self.fake_cursor.fetchall = MagicMock(return_value=[["v1"], ["v2"]])

        insp = inspect(self.session.bind)
        self.engine.dialect.server_version_info = (2, 0, 0)
        eq_(insp.get_view_names(schema="doc"), ["v1", "v2"])
        eq_(
            self.executed_statement,
            "SELECT table_name FROM information_schema.views "
            "WHERE table_schema = ? ORDER BY table_name ASC",
        )

    def test_get_view_definition(self):
        self.init_mock()
        self.fake_cursor.fetchone = MagicMock(return_value=["SELECT 1"])
        insp = inspect(self.session.bind)
        eq_(insp.get_view_definition("v1", schema="doc"), "SELECT 1")
        in_("SELECT view_definition FROM information_schema.views", self.executed_statement)

    def test_get_view_definition_missing(self):
        self.init_mock()
        self.fake_cursor.fetchone = MagicMock(return_value=None)
        insp = inspect(self.session.bind)
        with self.assertRaises(sa.exc.NoSuchTableError):
            insp.get_view_definition("missing", schema="doc")

    def test_get_columns_nullable(self):
        self.init_mock(
            return_value=[["id", "integer", False], ["code", "integer", False], ["x", "text", True]]
        )
        insp = inspect(self.session.bind)
        columns = insp.get_columns("t", schema="doc")
        eq_(
            [(c["name"], c["nullable"]) for c in columns],
            [("id", False), ("code", False), ("x", True)],
        )
        in_("is_nullable", self.executed_statement)

    @skipIf(SA_VERSION < SA_1_4, "Inspector.has_table only available on SQLAlchemy>=1.4")
    def test_has_table(self):
        self.init_mock(return_value=[["foo"], ["bar"]])
        insp = inspect(self.session.bind)
        is_true(insp.has_table("bar"))
        eq_(
            self.executed_statement,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ? "
            "AND table_type IN ('BASE TABLE', 'VIEW')",
        )

    @skipIf(SA_VERSION < SA_1_4, "Inspector.has_table only available on SQLAlchemy>=1.4")
    def test_has_table_view(self):
        # Not a base table, but a view.
        self.fake_cursor.rowcount = 1
        self.fake_cursor.description = (("foo", None, None, None, None, None, None),)
        self.fake_cursor.fetchall = MagicMock(return_value=[["v1"]])
        insp = inspect(self.session.bind)
        is_true(insp.has_table("v1"))
        in_("'VIEW'", self.executed_statement)

    @skipIf(SA_VERSION < SA_2_0, "Inspector.has_schema only available on SQLAlchemy>=2.0")
    def test_has_schema(self):
        self.init_mock(
            return_value=[["blob"], ["doc"], ["information_schema"], ["pg_catalog"], ["sys"]]
        )
        insp = inspect(self.session.bind)
        is_true(insp.has_schema("doc"))
        eq_(
            self.executed_statement,
            "select schema_name from information_schema.schemata order by schema_name asc",
        )

    def test_isolation_level(self):
        self.engine.dialect.set_isolation_level(self.connection, "FOO")
        assert self.engine.dialect.get_isolation_level(self.connection) == "AUTOCOMMIT"
        assert self.engine.dialect.get_isolation_level_values(self.connection) == ()
        self.engine.execution_options(isolation_level="AUTOCOMMIT")

    def test_default_paramstyle_is_pyformat(self):
        """
        Verify CrateDialect.default_paramstyle must be "pyformat"
        so that SQLAlchemy generates %(name)s placeholders.
        """
        eq_(self.engine.dialect.default_paramstyle, "pyformat")


@patch("crate.client.connection.Cursor", FakeCursor)
class SqlAlchemyDialectUrlSchemaTest(TestCase):
    """
    Reflection uses the `schema` URL parameter that `get_table_names` lists from.
    """

    def setUp(self):
        self.fake_cursor = MagicMock(name="fake_cursor")
        FakeCursor.return_value = self.fake_cursor
        self.parameters = []

        def execute(query, parameters=None, *args, **kwargs):
            self.parameters.append(parameters)
            return self.fake_cursor

        self.fake_cursor.execute = execute
        self.fake_cursor.rowcount = 1
        self.fake_cursor.description = (("foo", None, None, None, None, None, None),)
        self.engine = sa.create_engine("crate://?schema=sales")
        self.engine.connect().close()
        self.engine.dialect.server_version_info = (5, 10, 0)

    def test_get_columns(self):
        self.fake_cursor.fetchall = MagicMock(return_value=[["id", "integer", False]])
        inspect(self.engine).get_columns("t")
        eq_(self.parameters[-1][:2], ("t", "sales"))

    def test_get_pk_constraint(self):
        self.fake_cursor.fetchall = MagicMock(return_value=[["id"]])
        eq_(inspect(self.engine).get_pk_constraint("t")["constrained_columns"], ["id"])
        eq_(self.parameters[-1], ("t", "sales"))

    def test_get_view_names(self):
        self.fake_cursor.fetchall = MagicMock(return_value=[["v1"]])
        eq_(inspect(self.engine).get_view_names(), ["v1"])
        eq_(self.parameters[-1], ("sales",))

    def test_explicit_schema_wins(self):
        self.fake_cursor.fetchall = MagicMock(return_value=[["id"]])
        inspect(self.engine).get_pk_constraint("t", schema="other")
        eq_(self.parameters[-1], ("t", "other"))
