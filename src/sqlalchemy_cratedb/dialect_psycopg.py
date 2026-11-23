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

import datetime as dt
import re
import uuid

import sqlalchemy as sa
from sqlalchemy import types as sqltypes
from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy.engine import default
from sqlalchemy.pool import AsyncAdaptedQueuePool
from verlib2 import Version

from .sa_version import SA_VERSION

MIN_SQLALCHEMY_VERSION = Version("2.0.44")
MIN_PSYCOPG_VERSION = Version("3.3.9")

if SA_VERSION < MIN_SQLALCHEMY_VERSION:
    raise ImportError(
        f"The crate+psycopg dialect requires SQLAlchemy>={MIN_SQLALCHEMY_VERSION}, "
        f"found {sa.__version__}. Install it with `pip install 'sqlalchemy-cratedb[psycopg]'`."
    )

from .dialect import UUID, CrateDialect, Date, DateTime  # noqa: E402
from .dialect import colspecs as crate_colspecs  # noqa: E402
from .type.geo import Geopoint  # noqa: E402


class _Date_psycopg(Date):
    def result_processor(self, dialect, coltype):
        process_http = super().result_processor(dialect, coltype)

        def process(value):
            if isinstance(value, dt.datetime):
                if value.tzinfo is not None:
                    value = value.astimezone(dt.timezone.utc)
                return value.date()
            if isinstance(value, dt.date):
                return value
            return process_http(value)

        return process


class _DateTime_psycopg(DateTime):
    def result_processor(self, dialect, coltype):
        process_http = super().result_processor(dialect, coltype)

        def process(value):
            if isinstance(value, dt.datetime) and value.tzinfo is not None:
                value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
            return process_http(value)

        return process


class _Geopoint_psycopg(Geopoint):
    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                return tuple(float(part) for part in value.strip("()").split(","))
            return tuple(value)

        return process


class _UUID_psycopg(UUID):
    def result_processor(self, dialect, coltype):
        as_uuid = self.as_uuid

        def process(value):
            if value is None:
                return None
            if isinstance(value, uuid.UUID):
                return value if as_uuid else str(value)
            return uuid.UUID(value) if as_uuid else value

        return process


colspecs = {
    **crate_colspecs,
    sqltypes.Date: _Date_psycopg,
    sqltypes.DateTime: _DateTime_psycopg,
    sqltypes.TIMESTAMP: _DateTime_psycopg,
    sqltypes.UUID: _UUID_psycopg,
    Geopoint: _Geopoint_psycopg,
}


class _QmarkConnection:
    """
    [W1] The reflection queries of `CrateDialect` use `?` placeholders, which
    psycopg does not know. Remove once they use SQLAlchemy binds.
    """

    def __init__(self, connection):
        self._connection = connection

    def exec_driver_sql(self, statement, parameters=None, *args, **kwargs):
        return self._connection.exec_driver_sql(
            statement.replace("?", "%s"), parameters, *args, **kwargs
        )

    def __getattr__(self, name):
        return getattr(self._connection, name)


def _import_psycopg():
    import psycopg

    if Version(psycopg.__version__) < MIN_PSYCOPG_VERSION:
        raise ImportError(
            f"The crate+psycopg dialect requires psycopg>={MIN_PSYCOPG_VERSION}, "
            f"found {psycopg.__version__}. "
            "Install it with `pip install 'sqlalchemy-cratedb[psycopg]'`."
        )
    return psycopg


def _parse_prepare_threshold(value):
    if value is None or str(value).lower() == "none":
        return None
    return int(value)


class CrateDialect_psycopg(CrateDialect):
    driver = "psycopg"
    default_paramstyle = "pyformat"
    supports_statement_cache = True
    supports_native_decimal = True
    colspecs = colspecs

    # [W15] CrateDB bug: many errors are sent with the generic SQLSTATE XX000.
    # crate/crate#17489
    dbapi_exception_translation_map = {"InternalError_": "ProgrammingError"}

    @classmethod
    def import_dbapi(cls):
        return _import_psycopg()

    @classmethod
    def get_async_dialect_cls(cls, url):
        return CrateDialectAsync_psycopg

    def create_connect_args(self, url):
        opts = url.translate_connect_args(username="user", database="dbname")
        if "port" in opts:
            opts["port"] = int(opts["port"])
        opts.update(url.query)
        opts.pop("schema", None)

        hosts, ports = PGDialect._split_multihost_from_url(self, url)
        if hosts:
            opts["host"] = ",".join(hosts)
            if any(ports or ()):
                opts["port"] = ",".join(str(port) if port else "" for port in ports)

        opts.setdefault("user", "crate")
        opts.setdefault("dbname", "doc")
        opts["autocommit"] = True
        # [W3] CrateDB bug: a prepared `DROP TABLE` fails once the table is recreated.
        # crate/crate#20311
        opts["prepare_threshold"] = _parse_prepare_threshold(opts.get("prepare_threshold"))
        opts.setdefault("connect_timeout", 10)

        if opts.get("sslmode") in ("verify-ca", "verify-full") and "sslrootcert" not in opts:
            try:
                import certifi
            except ImportError:
                pass
            else:
                opts["sslrootcert"] = certifi.where()
        return [], opts

    def connect(self, *cargs, **cparams):
        return default.DefaultDialect.connect(self, *cargs, **cparams)

    def on_connect(self):
        from psycopg.types.json import JsonDumper

        def setup(dbapi_connection):
            self.set_isolation_level(dbapi_connection, "AUTOCOMMIT")
            self.get_driver_connection(dbapi_connection).adapters.register_dumper(dict, JsonDumper)

        return setup

    def get_isolation_level_values(self, dbapi_connection):
        return ("AUTOCOMMIT",)

    def set_isolation_level(self, dbapi_connection, level):
        dbapi_connection.autocommit = True

    def is_disconnect(self, e, connection, cursor):
        if isinstance(e, self.loaded_dbapi.Error) and connection is not None:
            return bool(connection.closed or connection.broken)
        return False

    def do_executemany(self, cursor, statement, parameters, context=None):
        # [W4] CrateDB bug: in psycopg's `executemany()`, a failed row is answered
        # with an update count psycopg cannot read, and the row is lost silently.
        # crate/crate#20593
        rowcount = 0
        for row in parameters:
            cursor.execute(statement, row)
            rowcount += max(cursor.rowcount, 0)
        if context is not None:
            context._rowcount = rowcount

    def _get_default_schema_name(self, connection):
        return connection.exec_driver_sql("SELECT current_schema()").scalar()

    def _get_server_version_info(self, connection):
        info = connection.connection.driver_connection.info
        version = info.parameter_status("crate_version")
        return tuple(int(part) for part in re.findall(r"\d+", version)[:3])

    def get_table_names(self, connection, schema=None, **kw):
        return super().get_table_names(_QmarkConnection(connection), schema=schema, **kw)

    def get_view_names(self, connection, schema=None, **kw):
        return super().get_view_names(_QmarkConnection(connection), schema=schema, **kw)

    def get_columns(self, connection, table_name, schema=None, **kw):
        return super().get_columns(_QmarkConnection(connection), table_name, schema=schema, **kw)

    def get_pk_constraint(self, engine, table_name, schema=None, **kw):
        return super().get_pk_constraint(_QmarkConnection(engine), table_name, schema=schema, **kw)


class CrateDialectAsync_psycopg(CrateDialect_psycopg):
    driver = "psycopg_async"
    is_async = True
    supports_statement_cache = True
    poolclass = AsyncAdaptedQueuePool

    @classmethod
    def import_dbapi(cls):
        from sqlalchemy.dialects.postgresql.psycopg import PGDialectAsync_psycopg

        _import_psycopg()
        return PGDialectAsync_psycopg.import_dbapi()

    def get_driver_connection(self, connection):
        return connection._connection


dialect = CrateDialect_psycopg
dialect_async = CrateDialectAsync_psycopg
