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

    [1] https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_sql.html
    [2] https://cratedb.com/docs/crate/reference/en/latest/interfaces/http.html#bulk-operations
    [3] https://github.com/pandas-dev/pandas/blob/v2.0.1/pandas/io/sql.py#L1011-L1027
    """  # noqa: E501

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
