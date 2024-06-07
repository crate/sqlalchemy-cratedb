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

import re
import sys
from unittest import TestCase
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.sql import select

from sqlalchemy_cratedb import SA_VERSION, SA_1_4
from sqlalchemy_cratedb.type import FloatVector

from crate.client.cursor import Cursor

from sqlalchemy_cratedb.type.vector import from_db, to_db

fake_cursor = MagicMock(name="fake_cursor")
FakeCursor = MagicMock(name="FakeCursor", spec=Cursor)
FakeCursor.return_value = fake_cursor


if SA_VERSION < SA_1_4:
    pytest.skip(reason="The FloatVector type is not supported on SQLAlchemy 1.3 and earlier", allow_module_level=True)


@patch("crate.client.connection.Cursor", FakeCursor)
class SqlAlchemyVectorTypeTest(TestCase):
    """
    Verify compilation of SQL statements where the schema includes the `FloatVector` type.
    """
    def setUp(self):
        self.engine = sa.create_engine("crate://")
        metadata = sa.MetaData()
        self.table = sa.Table(
            "testdrive",
            metadata,
            sa.Column("name", sa.String),
            sa.Column("data", FloatVector(3)),
        )
        self.session = Session(bind=self.engine)

    def assertSQL(self, expected_str, actual_expr):
        self.assertEqual(expected_str, str(actual_expr).replace('\n', ''))

    def test_create_invoke(self):
        self.table.create(self.engine)
        fake_cursor.execute.assert_called_with(
            (
                "\nCREATE TABLE testdrive (\n\t"
                "name STRING, \n\t"
                "data FLOAT_VECTOR(3)\n)\n\n"
            ),
            (),
        )

    def test_insert_invoke(self):
        stmt = self.table.insert().values(
            name="foo", data=[42.42, 43.43, 44.44]
        )
        with self.engine.connect() as conn:
            conn.execute(stmt)
        fake_cursor.execute.assert_called_with(
            ("INSERT INTO testdrive (name, data) VALUES (?, ?)"),
            ("foo", [42.42, 43.43, 44.44]),
        )

    def test_select_invoke(self):
        stmt = select(self.table.c.data)
        with self.engine.connect() as conn:
            conn.execute(stmt)
        fake_cursor.execute.assert_called_with(
            ("SELECT testdrive.data \nFROM testdrive"),
            (),
        )

    def test_sql_select(self):
        self.assertSQL(
            "SELECT testdrive.data FROM testdrive", select(self.table.c.data)
        )


def test_from_db_success():
    """
    Verify succeeding uses of `sqlalchemy_cratedb.type.vector.from_db`.
    """
    np = pytest.importorskip("numpy")
    assert from_db(None) is None
    assert np.array_equal(from_db(False), np.array(0., dtype=np.float32))
    assert np.array_equal(from_db(True), np.array(1., dtype=np.float32))
    assert np.array_equal(from_db(42), np.array(42, dtype=np.float32))
    assert np.array_equal(from_db(42.42), np.array(42.42, dtype=np.float32))
    assert np.array_equal(from_db([42.42, 43.43]), np.array([42.42, 43.43], dtype=np.float32))
    assert np.array_equal(from_db("42.42"), np.array(42.42, dtype=np.float32))
    assert np.array_equal(from_db(["42.42", "43.43"]), np.array([42.42, 43.43], dtype=np.float32))


def test_from_db_failure():
    """
    Verify failing uses of `sqlalchemy_cratedb.type.vector.from_db`.
    """
    pytest.importorskip("numpy")

    with pytest.raises(ValueError) as ex:
        from_db("foo")
    assert ex.match("could not convert string to float: 'foo'")

    with pytest.raises(ValueError) as ex:
        from_db(["foo"])
    assert ex.match("could not convert string to float: 'foo'")

    with pytest.raises(TypeError) as ex:
        from_db({"foo": "bar"})
    if sys.version_info < (3, 10):
        assert ex.match(re.escape("float() argument must be a string or a number, not 'dict'"))
    else:
        assert ex.match(re.escape("float() argument must be a string or a real number, not 'dict'"))


def test_to_db_success():
    """
    Verify succeeding uses of `sqlalchemy_cratedb.type.vector.to_db`.
    """
    np = pytest.importorskip("numpy")
    assert to_db(None) is None
    assert to_db(False) is False
    assert to_db(True) is True
    assert to_db(42) == 42
    assert to_db(42.42) == 42.42
    assert to_db([42.42, 43.43]) == [42.42, 43.43]
    assert to_db(np.array([42.42, 43.43])) == [42.42, 43.43]
    assert to_db("42.42") == "42.42"
    assert to_db("foo") == "foo"
    assert to_db(["foo"]) == ["foo"]
    assert to_db({"foo": "bar"}) == {"foo": "bar"}
    assert isinstance(to_db(object()), object)


def test_to_db_failure():
    """
    Verify failing uses of `sqlalchemy_cratedb.type.vector.to_db`.
    """
    np = pytest.importorskip("numpy")

    with pytest.raises(ValueError) as ex:
        to_db(np.array(["42.42", "43.43"]))
    assert ex.match("dtype must be numeric")

    with pytest.raises(ValueError) as ex:
        to_db(np.array([42.42, 43.43]), dim=33)
    assert ex.match("expected 33 dimensions, not 2")

    with pytest.raises(ValueError) as ex:
        to_db(np.array([[42.42, 43.43]]))
    assert ex.match("expected ndim to be 1")


def test_float_vector_no_dimension_size():
    """
    Verify a FloatVector can not be initialized without a dimension size.
    """
    engine = sa.create_engine("crate://")
    metadata = sa.MetaData()
    table = sa.Table(
        "foo",
        metadata,
        sa.Column("data", FloatVector),
    )
    with pytest.raises(ValueError) as ex:
        table.create(engine)
    ex.match("FloatVector must be initialized with dimension size")


def test_float_vector_as_generic():
    """
    Verify the `as_generic` and `python_type` method/property on the FloatVector type object.
    """
    fv = FloatVector(3)
    assert isinstance(fv.as_generic(), sa.ARRAY)
    assert fv.python_type is list
