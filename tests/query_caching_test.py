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

from unittest import TestCase, skipIf

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.sql.operators import eq

from sqlalchemy_cratedb import ObjectArray, ObjectType
from sqlalchemy_cratedb.sa_version import SA_1_4, SA_VERSION

try:
    from sqlalchemy.orm import declarative_base
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base

from tests.settings import crate_host


class SqlAlchemyQueryCompilationCaching(TestCase):
    def setUp(self):
        self.engine = sa.create_engine(f"crate://{crate_host}")
        self.metadata = sa.MetaData(schema="testdrive")
        self.session = Session(bind=self.engine)
        self.Character = self.setup_entity()
        # Without an `ObjectType` column, which would turn off caching for any
        # statement that selects the whole row.
        self.subscripts = sa.Table(
            "subscripts",
            self.metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("arr", sa.ARRAY(sa.Integer)),
            sa.Column("objarr", ObjectArray),
            sa.Column("js", sa.JSON),
        )

    def tearDown(self):
        self.session.close()
        self.metadata.drop_all(self.engine)

    def setup_entity(self):
        """
        Define ORM entity.
        """
        Base = declarative_base(metadata=self.metadata)

        class Character(Base):
            __tablename__ = "characters"
            name = sa.Column(sa.String, primary_key=True)
            age = sa.Column(sa.Integer)
            data = sa.Column(ObjectType)
            data_list = sa.Column(ObjectArray)

        return Character

    def setup_data(self):
        """
        Insert two records into the `characters` table.
        """
        self.metadata.drop_all(self.engine)
        self.metadata.create_all(self.engine)

        Character = self.Character
        char1 = Character(name="Trillian", data={"x": 1}, data_list=[{"foo": 1, "bar": 10}])
        char2 = Character(name="Slartibartfast", data={"y": 2}, data_list=[{"bar": 2}])
        self.session.add(char1)
        self.session.add(char2)
        self.session.commit()
        self.session.execute(sa.text("REFRESH TABLE testdrive.characters;"))

    def setup_subscript_data(self):
        """
        Insert one record into the `subscripts` table.
        """
        self.metadata.drop_all(self.engine)
        self.metadata.create_all(self.engine)
        with self.engine.connect() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO testdrive.subscripts (id, arr, objarr, js) VALUES "
                    "(1, [10, 20, 30], [{foo='F1', bar='B1'}, {foo='F2', bar='B2'}], "
                    "{x='JX', y='JY', \"it's\"='Q'})"
                )
            )
            connection.execute(sa.text("REFRESH TABLE testdrive.subscripts"))

    def execute_twice(self, first, second, first_params=None, second_params=None):
        """
        Execute two statements that share a cache key, and return both results.
        The second one must hit the cache, or the test proves nothing.
        """
        results = []
        with self.engine.connect() as connection:
            for statement, params in ((first, first_params), (second, second_params)):
                result = connection.execute(statement, params or {})
                results.append(result.rowcount if statement.is_dml else result.scalar())
            self.assertIs(connection.dialect.CACHE_HIT, result.context.cache_hit)
        return results

    @skipIf(SA_VERSION < SA_1_4, "On SA13, the 'ResultProxy' object has no attribute 'scalar_one'")
    def test_object_multiple_select_legacy(self):
        """
        The SQLAlchemy implementation of CrateDB's `OBJECT` type offers indexed
        access to the instance's content in form of a dictionary. Thus, it must
        not use `cache_ok = True` on its implementation, i.e. this part of the
        compiled SQL clause must not be cached.

        This test verifies that two subsequent `SELECT` statements are translated
        well, and don't trip on incorrect SQL compiled statement caching.

        This variant uses direct value matching on the `OBJECT`s attribute.
        """
        self.setup_data()
        Character = self.Character

        selectable = sa.select(Character).where(Character.data["x"] == 1)
        result = self.session.execute(selectable).scalar_one().data
        self.assertEqual({"x": 1}, result)

        selectable = sa.select(Character).where(Character.data["y"] == 2)
        result = self.session.execute(selectable).scalar_one().data
        self.assertEqual({"y": 2}, result)

    @skipIf(SA_VERSION < SA_1_4, "On SA13, the 'ResultProxy' object has no attribute 'scalar_one'")
    def test_object_multiple_select_modern(self):
        """
        The SQLAlchemy implementation of CrateDB's `OBJECT` type offers indexed
        access to the instance's content in form of a dictionary. Thus, it must
        not use `cache_ok = True` on its implementation, i.e. this part of the
        compiled SQL clause must not be cached.

        This test verifies that two subsequent `SELECT` statements are translated
        well, and don't trip on incorrect SQL compiled statement caching.

        This variant uses comparator method matching on the `OBJECT`s attribute.
        """
        self.setup_data()
        Character = self.Character

        selectable = sa.select(Character).where(Character.data["x"].as_integer() == 1)
        result = self.session.execute(selectable).scalar_one().data
        self.assertEqual({"x": 1}, result)

        selectable = sa.select(Character).where(Character.data["y"].as_integer() == 2)
        result = self.session.execute(selectable).scalar_one().data
        self.assertEqual({"y": 2}, result)

    @skipIf(SA_VERSION < SA_1_4, "On SA13, the 'ResultProxy' object has no attribute 'scalar_one'")
    def test_objectarray_multiple_select(self):
        """
        The `ObjectType` column of the entity turns off caching for these
        statements. `test_subscript_objectarray_key` covers the cached case.
        """
        self.setup_data()
        Character = self.Character

        selectable = sa.select(Character).where(Character.data_list["foo"].any(1, operator=eq))
        result = self.session.execute(selectable).scalar_one().data
        self.assertEqual({"x": 1}, result)

        selectable = sa.select(Character).where(Character.data_list["bar"].any(2, operator=eq))
        result = self.session.execute(selectable).scalar_one().data
        self.assertEqual({"y": 2}, result)

    @skipIf(SA_VERSION < SA_1_4, "SQLAlchemy 1.3 has no statement cache")
    def test_subscript_array_index(self):
        self.setup_subscript_data()
        arr = self.subscripts.c.arr
        self.assertEqual([10, 20], self.execute_twice(sa.select(arr[1]), sa.select(arr[2])))

    @skipIf(SA_VERSION < SA_1_4, "SQLAlchemy 1.3 has no statement cache")
    def test_subscript_array_index_bindparam(self):
        self.setup_subscript_data()
        statement = sa.select(self.subscripts.c.arr[sa.bindparam("pos")])
        self.assertEqual([10, 30], self.execute_twice(statement, statement, {"pos": 1}, {"pos": 3}))

    @skipIf(SA_VERSION < SA_1_4, "SQLAlchemy 1.3 has no statement cache")
    def test_subscript_array_index_expression_bindparam(self):
        self.setup_subscript_data()
        t = self.subscripts
        statement = sa.select(t.c.arr[t.c.id + sa.bindparam("off")])
        self.assertEqual([20, 30], self.execute_twice(statement, statement, {"off": 1}, {"off": 2}))
        with self.engine.connect() as connection:
            connection = connection.execution_options(compiled_cache=None)
            self.assertEqual(20, connection.execute(statement, {"off": 1}).scalar())

    @skipIf(SA_VERSION < SA_1_4, "SQLAlchemy 1.3 has no statement cache")
    def test_subscript_executemany(self):
        """
        SQLAlchemy does not support `literal_execute` with `executemany()`.
        """
        self.setup_subscript_data()
        t = self.subscripts
        statement = sa.delete(t).where(t.c.js["x"] == sa.bindparam("value"))
        parameters = [{"value": "JX"}, {"value": "unknown"}]
        with self.engine.connect() as connection:
            with self.assertRaises(sa.exc.StatementError) as cm:
                connection.execute(statement, parameters)
            self.assertIn("can't be used with executemany()", str(cm.exception))

            connection.execution_options(compiled_cache=None).execute(statement, parameters)
            connection.execute(sa.text("REFRESH TABLE testdrive.subscripts"))
            self.assertEqual(
                0, connection.execute(sa.select(sa.func.count()).select_from(t)).scalar()
            )

    @skipIf(SA_VERSION < SA_1_4, "SQLAlchemy 1.3 has a different `select()` signature")
    def test_subscript_expression_executemany(self):
        self.setup_subscript_data()
        t = self.subscripts
        statement = sa.delete(t).where(
            t.c.arr[t.c.id + sa.bindparam("off")] == sa.bindparam("value")
        )
        with self.engine.connect() as connection:
            connection.execute(statement, [{"off": 1, "value": 99}, {"off": 1, "value": 20}])
            connection.execute(sa.text("REFRESH TABLE testdrive.subscripts"))
            self.assertEqual(
                0, connection.execute(sa.select(sa.func.count()).select_from(t)).scalar()
            )

    @skipIf(SA_VERSION < SA_1_4, "SQLAlchemy 1.3 has no statement cache")
    def test_subscript_array_index_where(self):
        self.setup_subscript_data()
        t = self.subscripts
        self.assertEqual(
            [1, None],
            self.execute_twice(
                sa.select(t.c.id).where(t.c.arr[2] == 20),
                sa.select(t.c.id).where(t.c.arr[3] == 20),
            ),
        )

    @skipIf(SA_VERSION < SA_1_4, "SQLAlchemy 1.3 has no statement cache")
    def test_subscript_array_slice(self):
        self.setup_subscript_data()
        arr = self.subscripts.c.arr
        self.assertEqual(
            [[10, 20], [20, 30]], self.execute_twice(sa.select(arr[1:2]), sa.select(arr[2:3]))
        )

    @skipIf(SA_VERSION < SA_1_4, "SQLAlchemy 1.3 has no statement cache")
    def test_subscript_array_update(self):
        self.setup_subscript_data()
        t = self.subscripts
        self.assertEqual(
            [1, 1],
            self.execute_twice(
                sa.update(t).values({t.c.arr[1]: 99}), sa.update(t).values({t.c.arr[2]: 88})
            ),
        )
        with self.engine.connect() as connection:
            connection.execute(sa.text("REFRESH TABLE testdrive.subscripts"))
            self.assertEqual([99, 88, 30], connection.execute(sa.select(t.c.arr)).scalar())

    @skipIf(SA_VERSION < SA_1_4, "SQLAlchemy 1.3 has no statement cache")
    def test_subscript_objectarray_key(self):
        self.setup_subscript_data()
        objarr = self.subscripts.c.objarr
        self.assertEqual(
            [["F1", "F2"], ["B1", "B2"]],
            self.execute_twice(sa.select(objarr["foo"]), sa.select(objarr["bar"])),
        )

    @skipIf(SA_VERSION < SA_1_4, "SQLAlchemy 1.3 has no statement cache")
    def test_subscript_objectarray_index_key(self):
        self.setup_subscript_data()
        objarr = self.subscripts.c.objarr
        self.assertEqual(
            ["F1", "F2"],
            self.execute_twice(sa.select(objarr[1]["foo"]), sa.select(objarr[2]["foo"])),
        )

    @skipIf(SA_VERSION < SA_1_4, "SQLAlchemy 1.3 has no statement cache")
    def test_subscript_json_key(self):
        self.setup_subscript_data()
        js = self.subscripts.c.js
        self.assertEqual(["JX", "JY"], self.execute_twice(sa.select(js["x"]), sa.select(js["y"])))

    @skipIf(SA_VERSION < SA_1_4, "SQLAlchemy 1.3 has no statement cache")
    def test_subscript_json_key_with_quote(self):
        self.setup_subscript_data()
        js = self.subscripts.c.js
        self.assertEqual(["JX", "Q"], self.execute_twice(sa.select(js["x"]), sa.select(js["it's"])))
