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

from unittest import TestCase
from unittest.mock import MagicMock, patch

import sqlalchemy as sa
from crate.client.cursor import Cursor
from sqlalchemy.orm import Session, declarative_base, make_transient_to_detached

from sqlalchemy_cratedb import ObjectType


class UpdateExecutemanyTest(TestCase):
    def setUp(self):
        self.fake_cursor = MagicMock(name="fake_cursor")
        self.fake_cursor.description = ()
        self.fake_cursor.rowcount = 1
        fake_cursor_class = MagicMock(name="FakeCursor", spec=Cursor, return_value=self.fake_cursor)
        patcher = patch("crate.client.connection.Cursor", fake_cursor_class)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.engine = sa.create_engine("crate://")
        Base = declarative_base()

        class Item(Base):
            __tablename__ = "items"
            id = sa.Column(sa.Integer, primary_key=True)
            name = sa.Column(sa.String)
            data = sa.Column(ObjectType)

        self.Item = Item

    def persistent_items(self, session, count):
        """
        Attach `count` items to the session as if they had been loaded, without a SELECT.
        """
        items = [self.Item(id=i, name=f"item-{i}", data={"k": 1}) for i in range(1, count + 1)]
        for item in items:
            make_transient_to_detached(item)
            session.add(item)
        return items

    def expect_executemany(self, rows):
        """
        Mirror the driver, which sums the row counts of a bulk request.
        """
        self.fake_cursor.rowcount = rows
        self.fake_cursor.executemany.return_value = [{"rowcount": 1}] * rows

    def test_core_update_executemany(self):
        table = self.Item.__table__
        stmt = (
            table.update()
            .where(table.c.id == sa.bindparam("b_id"))
            .values(name=sa.bindparam("b_name"))
        )
        self.expect_executemany(2)
        with self.engine.connect() as connection:
            connection.execute(stmt, [{"b_id": 1, "b_name": "x"}, {"b_id": 2, "b_name": "y"}])

        self.fake_cursor.execute.assert_not_called()
        self.fake_cursor.executemany.assert_called_once()
        sql, parameter_sets = self.fake_cursor.executemany.call_args[0]
        self.assertEqual(sql, "UPDATE items SET name = %(b_name)s WHERE items.id = %(b_id)s")
        self.assertEqual(
            list(parameter_sets),
            [{"b_name": "x", "b_id": 1}, {"b_name": "y", "b_id": 2}],
        )

    def test_orm_flush_several_rows(self):
        session = Session(self.engine)
        items = self.persistent_items(session, 2)
        for item in items:
            item.name = "x"
        self.expect_executemany(2)
        session.flush()

        sql, parameter_sets = self.fake_cursor.executemany.call_args[0]
        self.assertEqual(sql, "UPDATE items SET name=%(name)s WHERE items.id = %(items_id)s")
        self.assertEqual(
            list(parameter_sets),
            [{"name": "x", "items_id": 1}, {"name": "x", "items_id": 2}],
        )

    def test_orm_flush_several_rows_object_type(self):
        """
        An `ObjectType` change in an executemany writes the whole object.
        """
        session = Session(self.engine)
        items = self.persistent_items(session, 2)
        for item in items:
            item.data["k"] = 2
        self.expect_executemany(2)
        session.flush()

        sql, parameter_sets = self.fake_cursor.executemany.call_args[0]
        self.assertEqual(sql, "UPDATE items SET data=%(data)s WHERE items.id = %(items_id)s")
        self.assertEqual(
            list(parameter_sets),
            [{"data": {"k": 2}, "items_id": 1}, {"data": {"k": 2}, "items_id": 2}],
        )

    def test_orm_flush_single_row_object_type_partial(self):
        session = Session(self.engine)
        (item,) = self.persistent_items(session, 1)
        item.data["k"] = 2
        session.flush()

        self.fake_cursor.executemany.assert_not_called()
        self.fake_cursor.execute.assert_called_once_with(
            "UPDATE items SET data['k'] = %(data_'k'_)s WHERE items.id = %(items_id)s",
            {"data_'k'_": 2, "items_id": 1},
        )
