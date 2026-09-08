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

import pytest
import sqlalchemy as sa

CORE_TYPE_FACTORIES = {
    "BigInteger": lambda: sa.BigInteger,
    "Boolean": lambda: sa.Boolean,
    "Date": lambda: sa.Date,
    "DateTime": lambda: sa.DateTime,
    "Double": lambda: sa.Double,
    "Enum": lambda: sa.Enum("a", "b", name="enum_a_b"),
    "Float": lambda: sa.Float,
    "Integer": lambda: sa.Integer,
    "Interval": lambda: sa.Interval,
    "JSON": lambda: sa.JSON,
    "LargeBinary": lambda: sa.LargeBinary,
    "Numeric": lambda: sa.Numeric,
    "PickleType": lambda: sa.PickleType,
    "SmallInteger": lambda: sa.SmallInteger,
    "String": lambda: sa.String(50),
    "Text": lambda: sa.Text,
    "Time": lambda: sa.Time,
    "Unicode": lambda: sa.Unicode(50),
    "UnicodeText": lambda: sa.UnicodeText,
    "Uuid": lambda: sa.Uuid,
    "ARRAY": lambda: sa.ARRAY(sa.Integer),
    "BIGINT": lambda: sa.BIGINT,
    "BINARY": lambda: sa.BINARY,
    "BLOB": lambda: sa.BLOB,
    "BOOLEAN": lambda: sa.BOOLEAN,
    "CHAR": lambda: sa.CHAR(5),
    "CLOB": lambda: sa.CLOB,
    "DATE": lambda: sa.DATE,
    "DATETIME": lambda: sa.DATETIME,
    "DECIMAL": lambda: sa.DECIMAL,
    "DOUBLE": lambda: sa.DOUBLE,
    "DOUBLE_PRECISION": lambda: sa.DOUBLE_PRECISION,
    "FLOAT": lambda: sa.FLOAT,
    "INTEGER": lambda: sa.INTEGER,
    "NCHAR": lambda: sa.NCHAR(5),
    "NUMERIC": lambda: sa.NUMERIC,
    "NVARCHAR": lambda: sa.NVARCHAR(50),
    "REAL": lambda: sa.REAL,
    "SMALLINT": lambda: sa.SMALLINT,
    "TEXT": lambda: sa.TEXT,
    "TIME": lambda: sa.TIME,
    "TIMESTAMP": lambda: sa.TIMESTAMP,
    "UUID": lambda: sa.UUID,
    "VARBINARY": lambda: sa.VARBINARY(50),
    "VARCHAR": lambda: sa.VARCHAR(50),
}

CORE_TYPES = {name: factory() for name, factory in CORE_TYPE_FACTORIES.items() if hasattr(sa, name)}


KNOWN_UNSUPPORTED = {
    "BINARY": "CrateDB has no binary data type",
    "BLOB": "CrateDB has no binary data type",
    "LargeBinary": "CrateDB has no binary data type",
    "PickleType": "Builds on `sa.LargeBinary`",
    "VARBINARY": "CrateDB has no binary data type",
}


def _cases():
    for name in sorted(CORE_TYPES):
        marks = []
        if name in KNOWN_UNSUPPORTED:
            marks.append(pytest.mark.xfail(strict=True, reason=KNOWN_UNSUPPORTED[name]))
        yield pytest.param(name, marks=marks)


@pytest.mark.parametrize("name", list(_cases()))
def test_core_type_is_creatable(cratedb_service, name):
    """CrateDB accepts the DDL the dialect generates for this type."""
    engine = cratedb_service.database.engine
    table = sa.Table(
        "type_coverage",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("d", CORE_TYPES[name]),
    )
    table.drop(engine, checkfirst=True)
    table.create(engine)
    table.drop(engine)
