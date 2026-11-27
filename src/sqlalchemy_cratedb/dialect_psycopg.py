import datetime as dt
import os
import re
import sys
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

try:
    from sqlalchemy.util.concurrency import await_
except ImportError:  # SQLAlchemy 2.0
    from sqlalchemy.util.concurrency import await_only as await_

EXECUTEMANY_MODES = ("bulk", "loop")


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
    The reflection queries of `CrateDialect` use `?` placeholders, which
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


def _pipeline_sync(connection, statement, parameters):
    cursors = []
    try:
        with connection.pipeline():
            for row in parameters:
                cursor = connection.cursor()
                cursors.append(cursor)
                cursor.execute(statement, row)
        return [cursor.rowcount for cursor in cursors]
    finally:
        for cursor in cursors:
            cursor.close()


async def _pipeline_async(connection, statement, parameters):
    cursors = []
    try:
        async with connection.pipeline():
            for row in parameters:
                cursor = connection.cursor()
                cursors.append(cursor)
                await cursor.execute(statement, row)
        return [cursor.rowcount for cursor in cursors]
    finally:
        for cursor in cursors:
            await cursor.close()


def _set_batch_result(context, counts):
    """
    Store the per-row counts of a batch as `crate://` does: `last_result` holds
    `{"rowcount": n}` per row, -2 for a failed row, and `rowcount` is the sum of
    the other rows, or -1 if every row failed.
    """
    if context is None:
        return
    context.last_result = [{"rowcount": n if n >= 0 else -2} for n in counts]
    succeeded = [n for n in counts if n >= 0]
    context._rowcount = sum(succeeded) if succeeded else -1


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


def _libpq_root_cert_configured():
    """
    Whether libpq finds a CA set of its own: `PGSSLROOTCERT`, or the default
    `~/.postgresql/root.crt` (`%APPDATA%\\postgresql\\root.crt` on Windows).
    """
    if os.environ.get("PGSSLROOTCERT"):
        return True
    if sys.platform == "win32":
        directory = os.path.join(os.environ.get("APPDATA", ""), "postgresql")
    else:
        directory = os.path.join(os.path.expanduser("~"), ".postgresql")
    return os.path.exists(os.path.join(directory, "root.crt"))


def _json_dumper():
    """
    A JSON dumper that converts values like `crate://` does: `datetime` and
    `date` to epoch milliseconds, `time` to ISO 8601, `Decimal` and `UUID` to
    strings.
    """
    from crate.client.http import json_dumps
    from psycopg.types.json import JsonDumper

    class CrateJsonDumper(JsonDumper):
        _dumps = staticmethod(json_dumps)

    return CrateJsonDumper


class CrateDialect_psycopg(CrateDialect):
    driver = "psycopg"
    default_paramstyle = "pyformat"
    supports_statement_cache = True
    supports_native_decimal = True
    colspecs = colspecs

    # CrateDB bug: many errors are sent with the generic SQLSTATE XX000.
    # crate/crate#17489
    dbapi_exception_translation_map = {"InternalError_": "ProgrammingError"}

    _insert_bulk_unnest = True

    def __init__(self, executemany_mode="bulk", **kwargs):
        super().__init__(**kwargs)
        if executemany_mode not in EXECUTEMANY_MODES:
            raise ValueError(
                f"executemany_mode={executemany_mode!r} is not supported, "
                f"use one of {', '.join(repr(mode) for mode in EXECUTEMANY_MODES)}"
            )
        self.executemany_mode = executemany_mode

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
        # CrateDB bug: a prepared `DROP TABLE` fails once the table is recreated.
        # crate/crate#20311
        opts["prepare_threshold"] = _parse_prepare_threshold(opts.get("prepare_threshold"))
        opts.setdefault("connect_timeout", 10)

        if (
            opts.get("sslmode") in ("verify-ca", "verify-full")
            and "sslrootcert" not in opts
            and not _libpq_root_cert_configured()
        ):
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
        json_dumper = _json_dumper()

        def setup(dbapi_connection):
            self.set_isolation_level(dbapi_connection, "AUTOCOMMIT")
            self.get_driver_connection(dbapi_connection).adapters.register_dumper(dict, json_dumper)

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
        # psycopg's own `executemany()` is never used. CrateDB bugs:
        # - a failed row is answered with an update count psycopg cannot read,
        #   and the row is lost silently. crate/crate#20593
        # - with `returning=True`, psycopg sends `Flush`, which CrateDB does not
        #   answer after a bind error, and the connection hangs. crate/crate#20633
        if self.executemany_mode == "loop":
            # One statement per row, so a key that matches nothing counts 0, not
            # -2 as in a bulk operation.
            counts = []
            for row in parameters:
                cursor.execute(statement, row)
                counts.append(cursor.rowcount)
        else:
            counts = self._executemany_pipeline(cursor, statement, parameters)
        _set_batch_result(context, counts)

    def _executemany_pipeline(self, cursor, statement, parameters):
        """
        Send every row in one pipeline with a single `Sync`, and read the
        count of each row. CrateDB runs the rows as one bulk operation, as
        `bulk_parameters` on `crate://`: a failed row does not stop the others,
        and psycopg reports its count as -1. pgwire does not send the error
        message of a failed row.
        """
        if self.is_async:
            connection = cursor._cursor.connection
            return await_(_pipeline_async(connection, statement, parameters))
        return _pipeline_sync(cursor.connection, statement, parameters)

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
