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


from unittest import TestCase, skipIf
from unittest.mock import MagicMock, patch

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.sql import operators

from sqlalchemy_cratedb import SA_1_4, SA_VERSION, ObjectArray

try:
    from sqlalchemy.orm import declarative_base
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base

from crate.client.cursor import Cursor

fake_cursor = MagicMock(name="fake_cursor")
FakeCursor = MagicMock(name="FakeCursor", spec=Cursor)
FakeCursor.return_value = fake_cursor


@patch("crate.client.connection.Cursor", FakeCursor)
class SqlAlchemyArrayTypeTest(TestCase):
    def setUp(self):
        self.engine = sa.create_engine("crate://")
        Base = declarative_base()
        self.metadata = sa.MetaData()

        class User(Base):
            __tablename__ = "users"

            name = sa.Column(sa.String, primary_key=True)
            friends = sa.Column(sa.ARRAY(sa.String))
            scores = sa.Column(sa.ARRAY(sa.Integer))

        self.User = User
        self.session = Session(bind=self.engine)
        self.subscripts = sa.Table(
            "subscripts",
            self.metadata,
            sa.Column("idx", sa.Integer),
            sa.Column("arr0", sa.ARRAY(sa.Integer, zero_indexes=True)),
            sa.Column("arr2d", sa.ARRAY(sa.Integer, dimensions=2)),
            sa.Column("data_list", ObjectArray),
        )

    def assertSQL(self, expected_str, actual_expr):
        self.assertEqual(expected_str, str(actual_expr).replace("\n", ""))

    def assertWhere(self, expected_where, clause):
        s = self.session.query(self.subscripts.c.idx).filter(clause)
        self.assertSQL(
            "SELECT subscripts.idx AS subscripts_idx FROM subscripts WHERE " + expected_where, s
        )

    @skipIf(SA_VERSION < SA_1_4, "`as_generic` not available with SQLAlchemy 1.3")
    def test_as_generic(self):
        t1 = sa.Table(
            "t",
            self.metadata,
            sa.Column("int_array", sa.ARRAY(sa.Integer)),
        )
        array_type = t1.c.int_array.type.as_generic()
        assert isinstance(array_type, sa.ARRAY)

    def test_create_with_array(self):
        t1 = sa.Table(
            "t",
            self.metadata,
            sa.Column("int_array", sa.ARRAY(sa.Integer)),
            sa.Column("str_array", sa.ARRAY(sa.String)),
        )
        t1.create(self.engine)
        fake_cursor.execute.assert_called_with(
            ("\nCREATE TABLE t (\n\tint_array ARRAY(INT), \n\tstr_array ARRAY(STRING)\n)\n\n"),
            sa.util.immutabledict({}),
        )

    def test_array_insert(self):
        trillian = self.User(name="Trillian", friends=["Arthur", "Ford"])
        self.session.add(trillian)
        self.session.commit()
        fake_cursor.execute.assert_called_with(
            (
                "INSERT INTO users (name, friends, scores) "
                "VALUES (%(name)s, %(friends)s, %(scores)s)"
            ),
            {"friends": ["Arthur", "Ford"], "name": "Trillian", "scores": None},
        )

    def test_any(self):
        s = self.session.query(self.User.name).filter(self.User.friends.any("arthur"))
        # SA 1.4+ uses the column name as the bind param; SA 1.3 uses a generic "param_1".
        param = "friends_1" if SA_VERSION >= SA_1_4 else "param_1"
        self.assertSQL(
            f"SELECT users.name AS users_name FROM users WHERE %({param})s = ANY (users.friends)",
            s,
        )

    def test_any_with_operator(self):
        s = self.session.query(self.User.name).filter(
            self.User.scores.any(6, operator=operators.lt)
        )
        # SA 1.4+ uses the column name as the bind param; SA 1.3 uses a generic "param_1".
        param = "scores_1" if SA_VERSION >= SA_1_4 else "param_1"
        self.assertSQL(
            f"SELECT users.name AS users_name FROM users WHERE %({param})s < ANY (users.scores)",
            s,
        )

    def test_index(self):
        s = self.session.query(self.User.name).filter(self.User.scores[1] == 5)
        self.assertSQL(
            "SELECT users.name AS users_name FROM users WHERE users.scores[1] = %(param_1)s", s
        )

    def test_index_zero_indexes(self):
        self.assertWhere("subscripts.arr0[1] = %(param_1)s", self.subscripts.c.arr0[0] == 5)

    def test_index_nested(self):
        self.assertWhere("subscripts.arr2d[1][2] = %(param_1)s", self.subscripts.c.arr2d[1][2] == 5)

    def test_index_column(self):
        t = self.subscripts
        self.assertWhere(
            "subscripts.arr0[(subscripts.idx + %(idx_1)s)] = %(param_1)s", t.c.arr0[t.c.idx] == 5
        )

    def test_index_expression(self):
        s = self.session.query(self.User.name).filter(
            self.User.scores[sa.func.char_length(self.User.name) + 1] == 5
        )
        self.assertSQL(
            "SELECT users.name AS users_name FROM users "
            "WHERE users.scores[(char_length(users.name) + %(char_length_1)s)] = %(param_1)s",
            s,
        )

    def test_index_expression_bindparam(self):
        s = self.session.query(self.User.name).filter(
            self.User.scores[sa.func.char_length(self.User.name) + sa.bindparam("off")] == 5
        )
        self.assertSQL(
            "SELECT users.name AS users_name FROM users "
            "WHERE users.scores[(char_length(users.name) + %(off)s)] = %(param_1)s",
            s,
        )

    def test_index_zero_indexes_bindparam(self):
        self.assertWhere(
            "subscripts.arr0[(%(pos)s + %(param_1)s)] = %(param_2)s",
            self.subscripts.c.arr0[sa.bindparam("pos")] == 5,
        )

    def test_index_type_coerce(self):
        s = self.session.query(self.User.name).filter(
            self.User.scores[sa.type_coerce(sa.literal(2), sa.Integer)] == 5
        )
        self.assertSQL(
            "SELECT users.name AS users_name FROM users WHERE users.scores[2] = %(param_1)s", s
        )

    @skipIf(SA_VERSION < SA_1_4, "SQLAlchemy 1.3 has no `literal_execute`")
    def test_index_bindparam(self):
        s = self.session.query(self.User.name).filter(self.User.scores[sa.bindparam("pos")] == 5)
        self.assertSQL(
            "SELECT users.name AS users_name FROM users "
            "WHERE users.scores[__[POSTCOMPILE_pos]] = %(param_1)s",
            s,
        )

    @skipIf(SA_VERSION >= SA_1_4, "SQLAlchemy 1.4+ renders the parameter on execution")
    def test_index_bindparam_sa13(self):
        s = self.session.query(self.User.name).filter(self.User.scores[sa.bindparam("pos")] == 5)
        with self.assertRaises(sa.exc.CompileError) as cm:
            str(s)
        self.assertEqual(
            "A subscript taking its value on execution needs SQLAlchemy 1.4 or later",
            str(cm.exception),
        )

    def test_index_invalid(self):
        s = self.session.query(self.User.name).filter(self.User.scores[1.5] == 5)
        with self.assertRaises(sa.exc.CompileError) as cm:
            str(s)
        self.assertEqual(
            "CrateDB subscripts take an integer index or a string key, not 1.5", str(cm.exception)
        )

    def test_slice(self):
        s = self.session.query(self.User.name).filter(self.User.scores[1:2] == [5])
        self.assertSQL(
            "SELECT users.name AS users_name FROM users "
            "WHERE users.scores[%(scores_1)s:%(scores_2)s] = %(param_1)s",
            s,
        )

    def test_slice_open(self):
        s = self.session.query(self.User.name).filter(self.User.scores[:2] == [5])
        self.assertSQL(
            "SELECT users.name AS users_name FROM users "
            "WHERE users.scores[:%(scores_1)s] = %(param_1)s",
            s,
        )
        s = self.session.query(self.User.name).filter(self.User.scores[2:] == [5])
        self.assertSQL(
            "SELECT users.name AS users_name FROM users "
            "WHERE users.scores[%(scores_1)s:] = %(param_1)s",
            s,
        )

    def test_slice_step(self):
        s = self.session.query(self.User.name).filter(self.User.scores[1:3:2] == [5])
        with self.assertRaises(sa.exc.CompileError) as cm:
            str(s)
        self.assertEqual("CrateDB array slices do not support a step", str(cm.exception))

    def test_update_element(self):
        stmt = sa.update(self.User.__table__).values({self.User.scores[1]: 99})
        self.assertSQL("UPDATE users SET scores[1] = %(param_1)s", stmt.compile(bind=self.engine))

    def test_object_array_key(self):
        self.assertWhere(
            "%(param_1)s = ANY (subscripts.data_list['foo'])",
            self.subscripts.c.data_list["foo"].any(1),
        )

    def test_object_array_index_key(self):
        self.assertWhere(
            "subscripts.data_list[1]['foo'] = %(param_1)s",
            self.subscripts.c.data_list[1]["foo"] == 1,
        )

    def test_multidimensional_arrays(self):
        t1 = sa.Table(
            "t",
            self.metadata,
            sa.Column("unsupported_array", sa.ARRAY(sa.Integer, dimensions=2)),
        )
        err = None
        try:
            t1.create(self.engine)
        except NotImplementedError as e:
            err = e
        self.assertEqual(str(err), "CrateDB doesn't support multidimensional arrays")
