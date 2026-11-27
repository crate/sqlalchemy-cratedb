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
import logging
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import sqlalchemy as sa

from sqlalchemy_cratedb.sa_version import SA_2_0, SA_VERSION

logger = logging.getLogger(__name__)


def insert_bulk(pd_table, conn, keys, data_iter):
    """
    Use CrateDB's "bulk operations" endpoint as a fast path for pandas' and Dask's `to_sql()` [1] method.

    The idea is to break out of SQLAlchemy, compile the insert statement, and use the raw
    DBAPI connection client, in order to invoke a request using `bulk_parameters` [2]::

        cursor.execute(sql=sql, bulk_parameters=data)

    The vanilla implementation, used by SQLAlchemy, is::

        data = [dict(zip(keys, row)) for row in data_iter]
        conn.execute(pd_table.table.insert(), data)

    Batch chunking will happen outside of this function, for example [3] demonstrates
    the relevant code in `pandas.io.sql`.

    Over the PostgreSQL wire protocol (`crate+psycopg://`) each chunk is one
    `INSERT ... SELECT ... FROM UNNEST(...)`.

    [1] https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_sql.html
    [2] https://cratedb.com/docs/crate/reference/en/latest/interfaces/http.html#bulk-operations
    [3] https://github.com/pandas-dev/pandas/blob/v2.0.1/pandas/io/sql.py#L1011-L1027
    """  # noqa: E501

    if conn.dialect._insert_bulk_unnest:
        return _insert_bulk_unnest(pd_table, conn, keys, data_iter)

    # Compile SQL statement and materialize batch.
    sql = str(pd_table.table.insert().compile(bind=conn))
    data = list(data_iter)

    # For debugging and tracing the batches running through this method.
    if logger.level == logging.DEBUG:
        logger.debug(f"Bulk SQL:     {sql}")
        logger.debug(f"Bulk records: {len(data)}")
        # logger.debug(f"Bulk data:    {data}")  # noqa: ERA001

    # Invoke bulk insert operation.
    cursor = conn._dbapi_connection.cursor()
    cursor.execute(sql=sql, bulk_parameters=data)
    cursor.close()
    return None


def _is_list_value(value):
    return isinstance(value, (list, tuple)) or getattr(value, "ndim", 0) > 0


def _escape_percent(sql):
    return sql.replace("%", "%%")


def _insert_bulk_unnest(pd_table, conn, keys, data_iter):
    """
    One statement per chunk:

        INSERT INTO t (a, b) SELECT * FROM UNNEST(%s::TEXT[], %s::BIGINT[])

    Each array is cast to the type pandas gives its column: psycopg sends a list
    of strings as an array of unknown type and CrateDB parses as JSON.

    `UNNEST` flattens an array of arrays, so a chunk with list values, as for
    `ARRAY`, `FLOAT_VECTOR` or `GEO_POINT` columns, is sent as one array of row
    objects instead. Without a cast, CrateDB converts each field to the type of
    its column. So is a chunk with a column of only NULLs, whose real type may
    not be the one pandas gives it, like `TEXT` for an object column::

        INSERT INTO t (a, b) SELECT r['a'], r['b'] FROM UNNEST(%s::ARRAY(OBJECT)) AS u (r)
    """
    rows = list(data_iter)
    if not rows:
        return 0
    dialect = conn.dialect
    preparer = dialect.identifier_preparer
    table = pd_table.table
    # The preparer doubles `%` in identifiers already.
    target = "{table} ({columns})".format(
        table=preparer.format_table(table),
        columns=", ".join(preparer.quote(key) for key in keys),
    )

    if any(_is_list_value(value) for row in rows for value in row) or any(
        all(value is None for value in column) for column in zip(*rows)
    ):
        return _insert_row_objects(conn, target, keys, rows)

    sql = "INSERT INTO {target} SELECT * FROM UNNEST({arrays})".format(
        target=target,
        arrays=", ".join(
            "%s::{}[]".format(dialect.type_compiler.process(table.c[key].type)) for key in keys
        ),
    )
    logger.debug("Bulk SQL:     %s", sql)
    logger.debug("Bulk records: %s", len(rows))
    return conn.exec_driver_sql(sql, tuple(list(column) for column in zip(*rows))).rowcount


def _insert_row_objects(conn, target, keys, rows):
    fields = ", ".join(
        "r[{}]".format(_escape_percent("'{}'".format(key.replace("'", "''")))) for key in keys
    )
    sql = "INSERT INTO {target} SELECT {fields} FROM UNNEST(%s::ARRAY(OBJECT)) AS u (r)".format(
        target=target, fields=fields
    )

    objects = [
        {
            key: value.tolist() if getattr(value, "ndim", 0) > 0 else value
            for key, value in zip(keys, row)
        }
        for row in rows
    ]
    logger.debug("Bulk SQL:     %s", sql)
    logger.debug("Bulk records: %s", len(rows))

    # CrateDB treats a key that holds null as unknown: `r['key']` raises "does not
    # contain the key", and `INSERT ... SELECT` skips that row without an error.
    # With `error_on_unknown_object_key = false`, the field reads as NULL. The
    # connection returns to the pool afterwards.
    previous = conn.exec_driver_sql("SHOW error_on_unknown_object_key").scalar()
    conn.exec_driver_sql("SET SESSION error_on_unknown_object_key = false")
    try:
        return conn.exec_driver_sql(sql, (objects,)).rowcount
    finally:
        conn.exec_driver_sql(
            "SET SESSION error_on_unknown_object_key = {}".format(
                "true" if str(previous).lower() in ("true", "on", "t", "1") else "false"
            )
        )


@contextmanager
def table_kwargs(**kwargs):
    """
    Context manager for adding SQLAlchemy dialect-specific table options at runtime.

    In certain cases where SQLAlchemy orchestration is implemented within a
    framework, like at this spot [1] in pandas' `SQLTable._create_table_setup`,
    it is not easily possible to forward SQLAlchemy dialect options at table
    creation time.

    In order to augment the SQL DDL statement to make it honor database-specific
    dialect options, the only way to work around the unfortunate situation is by
    monkey-patching the call to `sa.Table()` at runtime, relaying additional
    dialect options through corresponding keyword arguments in their original
    `<dialect>_<kwarg>` format [2].

    [1] https://github.com/pandas-dev/pandas/blob/v2.2.2/pandas/io/sql.py#L1282-L1285
    [2] https://docs.sqlalchemy.org/en/20/core/foundation.html#sqlalchemy.sql.base.DialectKWArgs.dialect_kwargs
    """

    if SA_VERSION < SA_2_0:
        _init_dist = sa.sql.schema.Table._init

        def _init(self, name, metadata, *args, **kwargs_effective):
            kwargs_effective.update(kwargs)
            return _init_dist(self, name, metadata, *args, **kwargs_effective)

        with patch("sqlalchemy.sql.schema.Table._init", _init):
            yield

    else:
        new_dist = sa.sql.schema.Table._new

        def _new(cls, *args: Any, **kw: Any) -> Any:
            kw.update(kwargs)
            table = new_dist(cls, *args, **kw)
            return table

        with patch("sqlalchemy.sql.schema.Table._new", _new):
            yield
