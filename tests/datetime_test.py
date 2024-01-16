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

import datetime as dt
from unittest import TestCase, skipIf
from unittest.mock import patch, MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from sqlalchemy_cratedb import SA_VERSION, SA_1_4
from sqlalchemy_cratedb.dialect import DateTime

try:
    from sqlalchemy.orm import declarative_base
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from crate.client.cursor import Cursor


fake_cursor = MagicMock(name='fake_cursor')
FakeCursor = MagicMock(name='FakeCursor', spec=Cursor)
FakeCursor.return_value = fake_cursor


INPUT_DATE = dt.date(2009, 5, 13)
INPUT_DATETIME_NOTZ = dt.datetime(2009, 5, 13, 19, 00, 30, 123456)
INPUT_DATETIME_TZ = dt.datetime(2009, 5, 13, 19, 00, 30, 123456, tzinfo=zoneinfo.ZoneInfo("Europe/Kyiv"))
OUTPUT_DATE = INPUT_DATE
OUTPUT_TIMETZ_NOTZ = dt.time(19, 00, 30, 123000)
OUTPUT_TIMETZ_TZ = dt.time(16, 00, 30, 123000)
OUTPUT_DATETIME_NOTZ = dt.datetime(2009, 5, 13, 19, 00, 30, 123000)
OUTPUT_DATETIME_TZ = dt.datetime(2009, 5, 13, 16, 00, 30, 123000)


@skipIf(SA_VERSION < SA_1_4, "SQLAlchemy 1.3 suddenly has problems with these test cases")
@patch('crate.client.connection.Cursor', FakeCursor)
class SqlAlchemyDateAndDateTimeTest(TestCase):

    def setUp(self):
        self.engine = sa.create_engine('crate://')
        Base = declarative_base()

        class Character(Base):
            __tablename__ = 'characters'
            name = sa.Column(sa.String, primary_key=True)
            date = sa.Column(sa.Date)
            datetime = sa.Column(sa.DateTime)

        fake_cursor.description = (
            ('characters_name', None, None, None, None, None, None),
            ('characters_date', None, None, None, None, None, None)
        )
        self.session = Session(bind=self.engine)
        self.Character = Character

    def test_date_can_handle_datetime(self):
        """ date type should also be able to handle iso datetime strings.

        this verifies that the fallback in the Date result_processor works.
        """
        fake_cursor.fetchall.return_value = [
            ('Trillian', '2013-07-16T00:00:00.000Z')
        ]
        self.session.query(self.Character).first()

    def test_date_can_handle_tz_aware_datetime(self):
        character = self.Character()
        character.name = "Athur"
        character.datetime = INPUT_DATETIME_NOTZ
        self.session.add(character)


Base = declarative_base()


class FooBar(Base):
    __tablename__ = "foobar"
    name = sa.Column(sa.String, primary_key=True)
    date = sa.Column(sa.Date)
    datetime_notz = sa.Column(DateTime(timezone=False))
    datetime_tz = sa.Column(DateTime(timezone=True))


@pytest.fixture
def session(cratedb_service):
    engine = cratedb_service.database.engine
    session = sessionmaker(bind=engine)()

    Base.metadata.drop_all(engine, checkfirst=True)
    Base.metadata.create_all(engine, checkfirst=True)
    return session


@pytest.mark.skipif(SA_VERSION < SA_1_4, reason="Test case not supported on SQLAlchemy 1.3")
def test_datetime_notz(session):
    """
    An integration test for `sa.Date` and `sa.DateTime`, not using timezones.
    """

    # Insert record.
    foo_item = FooBar(
        name="foo",
        date=INPUT_DATE,
        datetime_notz=INPUT_DATETIME_NOTZ,
        datetime_tz=INPUT_DATETIME_NOTZ,
    )
    session.add(foo_item)
    session.commit()
    session.execute(sa.text("REFRESH TABLE foobar"))

    # Query record.
    result = session.execute(sa.select(
        FooBar.name, FooBar.date, FooBar.datetime_notz, FooBar.datetime_tz)).mappings().first()

    # Compare outcome.
    assert result["date"] == OUTPUT_DATE
    assert result["datetime_notz"] == OUTPUT_DATETIME_NOTZ
    assert result["datetime_notz"].tzname() is None
    assert result["datetime_notz"].timetz() == OUTPUT_TIMETZ_NOTZ
    assert result["datetime_notz"].tzinfo is None
    assert result["datetime_tz"] == OUTPUT_DATETIME_NOTZ
    assert result["datetime_tz"].tzname() is None
    assert result["datetime_tz"].timetz() == OUTPUT_TIMETZ_NOTZ
    assert result["datetime_tz"].tzinfo is None


@pytest.mark.skipif(SA_VERSION < SA_1_4, reason="Test case not supported on SQLAlchemy 1.3")
def test_datetime_tz(session):
    """
    An integration test for `sa.Date` and `sa.DateTime`, now using timezones.
    """

    # Insert record.
    foo_item = FooBar(
        name="foo",
        date=INPUT_DATE,
        datetime_notz=INPUT_DATETIME_TZ,
        datetime_tz=INPUT_DATETIME_TZ,
    )
    session.add(foo_item)
    session.commit()
    session.execute(sa.text("REFRESH TABLE foobar"))

    # Query record.
    session.expunge(foo_item)
    result = session.execute(sa.select(
        FooBar.name, FooBar.date, FooBar.datetime_notz, FooBar.datetime_tz)).mappings().first()

    # Compare outcome.
    assert result["date"] == OUTPUT_DATE
    assert result["datetime_notz"] == OUTPUT_DATETIME_NOTZ
    assert result["datetime_notz"].tzname() is None
    assert result["datetime_notz"].timetz() == OUTPUT_TIMETZ_NOTZ
    assert result["datetime_notz"].tzinfo is None
    assert result["datetime_tz"] == OUTPUT_DATETIME_TZ
    assert result["datetime_tz"].tzname() is None
    assert result["datetime_tz"].timetz() == OUTPUT_TIMETZ_TZ
    assert result["datetime_tz"].tzinfo is None


@pytest.mark.skipif(SA_VERSION < SA_1_4, reason="Test case not supported on SQLAlchemy 1.3")
def test_datetime_date(session):
    """
    Validate assigning a `date` object to a `datetime` column works.

    It is needed by meltano-tap-cratedb.

    The test suite of `meltano-tap-cratedb`, derived from the corresponding
    PostgreSQL adapter, will supply `dt.date` objects. Without this improvement,
    those will otherwise fail.
    """

    # Insert record.
    foo_item = FooBar(
        name="foo",
        datetime_notz=dt.date(2009, 5, 13),
        datetime_tz=dt.date(2009, 5, 13),
    )
    session.add(foo_item)
    session.commit()
    session.execute(sa.text("REFRESH TABLE foobar"))

    # Query record.
    result = session.execute(sa.select(FooBar.name, FooBar.date, FooBar.datetime_notz, FooBar.datetime_tz)).mappings().first()

    # Compare outcome.
    assert result["datetime_notz"] == dt.datetime(2009, 5, 13, 0, 0, 0)
    assert result["datetime_tz"] == dt.datetime(2009, 5, 13, 0, 0, 0)
