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

import base64
import pickle
from unittest import TestCase
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

try:
    from sqlalchemy.orm import declarative_base
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy_cratedb.type.binary import BinaryBase64

# CrateDB stores base64 text in a STRING column. Both clauses are required:
# without them, Lucene's 32766-byte term limit caps the payload at ~24 KB.
BINARY_COLUMN_DDL = "STRING INDEX OFF STORAGE WITH (columnstore = false)"

BINARY_TYPES = [
    sa.LargeBinary,
    sa.BLOB,
    sa.BINARY,
    sa.VARBINARY(50),
    sa.PickleType,
]


def column_spec(engine, type_, **kwargs):
    """Compile a single-column `CREATE TABLE` and return the column definition."""
    table = sa.Table(
        "t",
        sa.MetaData(),
        sa.Column("d", type_, **kwargs),
    )
    ddl = " ".join(str(CreateTable(table).compile(engine)).split())
    return ddl[ddl.index("( d ") + 4 : ddl.rindex(" )")]


class BinaryBase64ProcessorTest(TestCase):
    """The bind/result processors, in isolation."""

    def setUp(self):
        self.type = BinaryBase64()
        self.dialect = MagicMock()

    def test_bind_encodes_bytes_to_base64_string(self):
        process = self.type.bind_processor(self.dialect)
        self.assertEqual(process(b"hello world"), base64.b64encode(b"hello world").decode())

    def test_bind_encodes_arbitrary_binary_data(self):
        process = self.type.bind_processor(self.dialect)
        data = bytes(range(256))
        self.assertEqual(process(data), base64.b64encode(data).decode())

    def test_bind_returns_none_for_none_input(self):
        self.assertIsNone(self.type.bind_processor(self.dialect)(None))

    def test_result_decodes_base64_string_to_bytes(self):
        process = self.type.result_processor(self.dialect, None)
        self.assertEqual(process(base64.b64encode(b"hello world").decode()), b"hello world")

    def test_result_returns_none_for_none_input(self):
        self.assertIsNone(self.type.result_processor(self.dialect, None)(None))

    def test_round_trip(self):
        bind = self.type.bind_processor(self.dialect)
        result = self.type.result_processor(self.dialect, None)
        data = b"\x00\x01\x02\xff\xfe\xfd"
        self.assertEqual(result(bind(data)), data)


class BinaryDDLTest(TestCase):
    """DDL compilation for binary column types."""

    def setUp(self):
        self.engine = sa.create_engine("crate://")

    def test_binary_types_emit_unindexed_string(self):
        for type_ in BINARY_TYPES:
            with self.subTest(type=type_):
                self.assertEqual(column_spec(self.engine, type_), BINARY_COLUMN_DDL)

    def test_cast_does_not_carry_storage_clauses(self):
        """
        `visit_BLOB` also serves `CAST`, so the DDL-only clauses must be emitted
        by the DDL compiler instead. Guards against moving them back.
        """
        table = sa.table("t", sa.column("d"))
        compiled = str(sa.cast(table.c.d, sa.LargeBinary).compile(self.engine))
        self.assertEqual(compiled, "CAST(t.d AS STRING)")

    def test_explicit_options_do_not_duplicate_clauses(self):
        for kwargs in (
            {"crate_index": False},
            {"crate_columnstore": False},
            {"crate_index": False, "crate_columnstore": False},
        ):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(
                    column_spec(self.engine, sa.LargeBinary, **kwargs), BINARY_COLUMN_DDL
                )

    def test_columnstore_guard_still_applies_to_other_types(self):
        with self.assertRaises(sa.exc.CompileError):
            column_spec(self.engine, sa.Integer, crate_columnstore=False)

    def test_string_columns_are_unaffected(self):
        self.assertEqual(column_spec(self.engine, sa.Text), "STRING")


Base = declarative_base()


class Blobby(Base):
    __tablename__ = "binary_test"

    id = sa.Column(sa.Integer, primary_key=True)
    payload = sa.Column(sa.LargeBinary)
    pickled = sa.Column(sa.PickleType)


@pytest.fixture
def session(cratedb_service):
    engine = cratedb_service.database.engine
    session = sessionmaker(bind=engine)()

    Base.metadata.drop_all(engine, checkfirst=True)
    Base.metadata.create_all(engine, checkfirst=True)
    return session


def refresh(session):
    session.execute(sa.text("REFRESH TABLE binary_test"))


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"hello world", id="ascii"),
        pytest.param(b"", id="empty"),
        pytest.param(bytes(range(256)), id="all-byte-values"),
        pytest.param(b"\x00\x00\x00", id="null-bytes"),
        pytest.param("Ünïcödé ✓".encode(), id="utf8"),
        pytest.param(None, id="null"),
    ],
)
def test_roundtrip(session, payload):
    """Binary payloads survive a write/read cycle unchanged."""
    session.add(Blobby(id=1, payload=payload))
    session.commit()
    refresh(session)

    assert session.execute(sa.select(Blobby.payload)).scalar() == payload


def test_roundtrip_exceeds_lucene_term_limit(session):
    """
    A payload whose base64 encoding exceeds Lucene's 32766-byte term limit.

    This fails unless the column is created with `INDEX OFF` and
    `columnstore = false`; a plain STRING column caps out at ~24 KB of binary.
    """
    payload = bytes(range(256)) * 256  # 64 KiB, ~87 KiB once base64-encoded

    session.add(Blobby(id=1, payload=payload))
    session.commit()
    refresh(session)

    assert session.execute(sa.select(Blobby.payload)).scalar() == payload


def test_stored_representation_is_base64(session):
    """The column really does hold base64 text, readable by any other client."""
    session.add(Blobby(id=1, payload=b"hello world"))
    session.commit()
    refresh(session)

    stored = session.execute(sa.text("SELECT payload FROM binary_test")).scalar()
    assert stored == "aGVsbG8gd29ybGQ="


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(bytearray(b"bytearray"), id="bytearray"),
        pytest.param(memoryview(b"memoryview"), id="memoryview"),
    ],
)
def test_accepts_bytes_like_input(session, payload):
    session.add(Blobby(id=1, payload=payload))
    session.commit()
    refresh(session)

    assert session.execute(sa.select(Blobby.payload)).scalar() == bytes(payload)


def test_rejects_str_input(session):
    session.add(Blobby(id=1, payload="a plain str"))
    with pytest.raises(sa.exc.StatementError):
        session.commit()


def test_update(session):
    session.add(Blobby(id=1, payload=b"before"))
    session.commit()
    refresh(session)

    session.get(Blobby, 1).payload = b"after"
    session.commit()
    refresh(session)

    assert session.execute(sa.select(Blobby.payload)).scalar() == b"after"


def test_pickle_type(session):
    """`sa.PickleType` builds on `sa.LargeBinary`, so it rides along."""
    payload = {"nested": [1, 2, {"key": "value"}]}

    session.add(Blobby(id=1, pickled=payload))
    session.commit()
    refresh(session)

    assert session.execute(sa.select(Blobby.pickled)).scalar() == payload

    # The column holds base64 of the pickle stream, not raw bytes.
    stored = session.execute(sa.text("SELECT pickled FROM binary_test")).scalar()
    assert base64.b64decode(stored) == pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)


def test_filtering_works_without_index(session):
    """Equality filtering still resolves with indexing and the columnstore off."""
    session.add_all([Blobby(id=1, payload=b"needle"), Blobby(id=2, payload=b"haystack")])
    session.commit()
    refresh(session)

    ids = session.execute(sa.select(Blobby.id).where(Blobby.payload == b"needle")).scalars()
    assert list(ids) == [1]


def test_reflection_yields_string(session, cratedb_service):
    """
    Reflection cannot recover the binary type, because the column really is a
    STRING. A reflected table needs the binary type re-declared to round-trip
    as `bytes`. Pinned here so the limitation stays visible.
    """
    engine = cratedb_service.database.engine
    reflected = sa.Table("binary_test", sa.MetaData(), autoload_with=engine)

    assert isinstance(reflected.c.payload.type, sa.String)
    assert not isinstance(reflected.c.payload.type, sa.LargeBinary)
