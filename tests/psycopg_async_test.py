"""
The psycopg dialect, asyncio: `create_async_engine("crate+psycopg://...")`.
"""

import asyncio
import datetime as dt
import decimal
import os
import socket
import time
import types
import uuid
import warnings

import pytest
import sqlalchemy as sa
from verlib2 import Version

from sqlalchemy_cratedb.sa_version import SA_VERSION

if SA_VERSION < Version("2.0.44"):
    pytest.skip("The psycopg dialect requires SQLAlchemy 2.0.44", allow_module_level=True)

psycopg = pytest.importorskip("psycopg")

import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base  # noqa: E402

from sqlalchemy_cratedb import Geopoint, ObjectType, _psycopg_timeout  # noqa: E402
from sqlalchemy_cratedb.dialect_psycopg import CrateDialectAsync_psycopg  # noqa: E402
from sqlalchemy_cratedb.support import arefresh_table, refresh_after_dml  # noqa: E402


@pytest_asyncio.fixture
async def engine(cratedb_service):
    engine = create_async_engine(cratedb_service.psycopg_dburi)
    yield engine
    await engine.dispose()


@pytest.fixture
def http(cratedb_service):
    """
    A `crate://` connection, the reference for values and reflection.
    """
    engine = sa.create_engine(cratedb_service.http_dburi)
    with engine.connect() as connection:
        yield connection
    engine.dispose()


@pytest.mark.parametrize("url", ["crate+psycopg://", "crate+psycopg_async://"])
def test_url_selects_the_async_dialect(url):
    engine = create_async_engine(url)
    assert type(engine.dialect) is CrateDialectAsync_psycopg
    assert engine.dialect.driver == "psycopg_async"
    assert engine.dialect.is_async
    assert isinstance(engine.sync_engine.pool, sa.pool.AsyncAdaptedQueuePool)


def test_http_url_is_refused():
    with pytest.raises(sa.exc.ArgumentError, match=r"crate\+psycopg://"):
        create_async_engine("crate://")


@pytest.mark.asyncio
async def test_initialize(engine, http):
    async with engine.connect() as connection:
        assert (await connection.execute(sa.text("SELECT 1"))).scalar_one() == 1
        raw = await connection.get_raw_connection()
        assert isinstance(raw.driver_connection, psycopg.AsyncConnection)
        assert raw.driver_connection.autocommit
    assert engine.dialect.server_version_info == http.dialect.server_version_info
    assert engine.dialect.default_schema_name == "doc"


@pytest.mark.asyncio
async def test_connection_from_async_creator_runs_in_autocommit(cratedb_service):
    url = sa.engine.make_url(cratedb_service.psycopg_dburi)

    async def creator():
        return await psycopg.AsyncConnection.connect(
            host=url.host, port=url.port, user="crate", dbname="doc"
        )

    engine = create_async_engine(url, async_creator=creator)
    try:
        async with engine.connect() as connection:
            await connection.execute(sa.text("SELECT 1"))
            raw = await connection.get_raw_connection()
            assert raw.driver_connection.autocommit
            assert (
                raw.driver_connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_queries(cratedb_service):
    engine = create_async_engine(cratedb_service.psycopg_dburi, pool_size=5, max_overflow=0)

    async def query(sensor_id):
        async with engine.connect() as connection:
            result = await connection.execute(sa.text("SELECT :id"), {"id": sensor_id})
            return result.scalar_one()

    try:
        assert await asyncio.gather(*(query(i) for i in range(50))) == list(range(50))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pool_pre_ping_replaces_a_closed_connection(cratedb_service):
    engine = create_async_engine(
        cratedb_service.psycopg_dburi, pool_pre_ping=True, pool_size=1, max_overflow=0
    )
    try:
        async with engine.connect() as connection:
            first = (await connection.get_raw_connection()).driver_connection
            await first.close()
        async with engine.connect() as connection:
            assert (await connection.execute(sa.text("SELECT 1"))).scalar_one() == 1
            assert (await connection.get_raw_connection()).driver_connection is not first
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_all_and_reflection(engine, http):
    metadata = sa.MetaData()
    table = sa.Table(
        "psycopg_async_devices",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String),
        sa.Column("payload", ObjectType),
        crate_number_of_shards=3,
    )
    async with engine.connect() as connection:
        await connection.run_sync(metadata.drop_all, checkfirst=True)
        await connection.run_sync(metadata.create_all)
        try:
            shards = await connection.execute(
                sa.text(
                    "SELECT number_of_shards FROM information_schema.tables "
                    "WHERE table_name = 'psycopg_async_devices'"
                )
            )
            assert shards.scalar_one() == 3

            def reflect(sync_connection):
                inspector = sa.inspect(sync_connection)
                return (
                    inspector.get_table_names(),
                    str(inspector.get_columns(table.name)),
                    inspector.get_pk_constraint(table.name),
                )

            names, columns, pk = await connection.run_sync(reflect)
            reference = sa.inspect(http)
            assert table.name in names
            assert columns == str(reference.get_columns(table.name))
            assert pk == reference.get_pk_constraint(table.name)
        finally:
            await connection.run_sync(metadata.drop_all)


@pytest.mark.asyncio
async def test_dml_rowcount(engine):
    async with engine.connect() as connection:
        await connection.execute(sa.text("DROP TABLE IF EXISTS psycopg_async_rowcount"))
        await connection.execute(sa.text("CREATE TABLE psycopg_async_rowcount (id INT)"))
        try:
            await connection.execute(
                sa.text("INSERT INTO psycopg_async_rowcount VALUES (1), (2), (3)")
            )
            await arefresh_table(connection, "psycopg_async_rowcount")
            result = await connection.execute(
                sa.text("UPDATE psycopg_async_rowcount SET id = id + 10 WHERE id > 1")
            )
            assert result.rowcount == 2
            await arefresh_table(connection, "psycopg_async_rowcount")
            result = await connection.execute(
                sa.text("UPDATE psycopg_async_rowcount SET id = :new WHERE id = :old"),
                [{"new": 21, "old": 1}, {"new": 99, "old": 50}, {"new": 22, "old": 12}],
            )
            assert result.rowcount == 2
        finally:
            await connection.execute(sa.text("DROP TABLE psycopg_async_rowcount"))


@pytest.mark.asyncio
async def test_values_match_sync(engine, cratedb_service):
    metadata = sa.MetaData()
    table = sa.Table(
        "psycopg_async_values",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("day", sa.Date),
        sa.Column("measured_at", sa.DateTime),
        sa.Column("price", sa.Numeric(10, 2)),
        sa.Column("device_id", sa.Uuid),
        sa.Column("tags", sa.ARRAY(sa.String)),
        sa.Column("payload", ObjectType),
        sa.Column("location", Geopoint),
    )
    row = {
        "id": 1,
        "day": dt.date(2026, 10, 26),
        "measured_at": dt.datetime(2026, 10, 26, 12, 30, 1, 123000),
        "price": decimal.Decimal("1.50"),
        "device_id": uuid.UUID("6f0c7b6e-6a3e-4e53-8c0b-0d6c7a1b2c3d"),
        "tags": ["indoor", "calibrated"],
        "payload": {"unit": "celsius", "calibration": {"offset": 0.5}},
        "location": (10.95667, 47.18917),
    }
    nulls = dict.fromkeys(row) | {"id": 2}
    async with engine.connect() as connection:
        await connection.run_sync(metadata.drop_all, checkfirst=True)
        await connection.run_sync(metadata.create_all)
        await connection.execute(table.insert(), [row, nulls])
        await arefresh_table(connection, table)
        ours = (await connection.execute(sa.select(table).order_by(table.c.id))).all()

    sync_engine = sa.create_engine(cratedb_service.psycopg_dburi)
    try:
        with sync_engine.connect() as connection:
            theirs = connection.execute(sa.select(table).order_by(table.c.id)).all()
        assert ours == theirs
        assert [type(value) for value in ours[0]] == [type(value) for value in theirs[0]]
        assert ours[0].payload == row["payload"]
        assert ours[0].day == row["day"]
        assert tuple(ours[1]) == (2,) + (None,) * (len(row) - 1)
    finally:
        metadata.drop_all(sync_engine)
        sync_engine.dispose()


@pytest.mark.asyncio
async def test_sql_errors(engine):
    async with engine.connect() as connection:
        await connection.execute(sa.text("DROP TABLE IF EXISTS psycopg_async_readings"))
        await connection.execute(
            sa.text("CREATE TABLE psycopg_async_readings (id INT, value INT CHECK (value >= 0))")
        )
        try:
            with pytest.raises(sa.exc.ProgrammingError, match="Failed CONSTRAINT") as excinfo:
                await connection.execute(
                    sa.text("INSERT INTO psycopg_async_readings VALUES (1, -1)")
                )
            assert excinfo.value.orig.sqlstate == "XX000"
            with pytest.raises(sa.exc.ProgrammingError):
                await connection.execute(sa.text("SELECT * FROM unknown_readings"))
            assert (await connection.execute(sa.text("SELECT 2"))).scalar_one() == 2
        finally:
            await connection.execute(sa.text("DROP TABLE psycopg_async_readings"))


@pytest.mark.asyncio
async def test_session_with_refresh_after_dml(engine):
    """
    With `refresh_after_dml`, a committed row is visible to the next query.
    """
    Base = declarative_base()

    class Device(Base):
        __tablename__ = "psycopg_async_session_devices"
        id = sa.Column(sa.String, primary_key=True)
        location = sa.Column(Geopoint)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all, checkfirst=True)
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    refresh_after_dml(session_factory)
    try:
        async with session_factory() as session:
            session.add(Device(id="sensor-1", location=(10.95667, 47.18917)))
            await session.commit()
            device = (await session.execute(sa.select(Device))).scalar_one()
            assert device.location == pytest.approx((10.95667, 47.18917))

            device.location = (13.4050, 52.5200)
            await session.commit()
            await session.refresh(device)
            assert device.location == pytest.approx((13.4050, 52.5200))

            await session.delete(device)
            await session.commit()
            assert (await session.execute(sa.select(Device))).first() is None
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_orm_object_partial_update(engine, http):
    """
    A change to one key of an `ObjectType` is written as `payload['key'] = ...`,
    as on `crate://`. A deleted key becomes null.
    """
    Base = declarative_base()

    class Device(Base):
        __tablename__ = "psycopg_async_object_devices"
        id = sa.Column(sa.Integer, primary_key=True)
        payload = sa.Column(ObjectType)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all, checkfirst=True)
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            Device.__table__.insert(), {"id": 1, "payload": {"firmware": "1.0", "room": "lab"}}
        )
        await arefresh_table(connection, Device.__table__)
    try:
        async with AsyncSession(engine) as session:
            device = await session.get(Device, 1)
            device.payload["firmware"] = "1.1"
            del device.payload["room"]
            await session.commit()
        http.exec_driver_sql("REFRESH TABLE psycopg_async_object_devices")
        stored = http.exec_driver_sql("SELECT payload FROM psycopg_async_object_devices").scalar()
        assert stored == {"firmware": "1.1", "room": None}
    finally:
        Base.metadata.drop_all(http)


@pytest.mark.asyncio
async def test_no_statement_cache_warning(engine):
    with warnings.catch_warnings():
        warnings.simplefilter("error", sa.exc.SAWarning)
        async with engine.connect() as connection:
            await connection.execute(sa.select(sa.literal(1)))


def async_connect_args(url):
    return create_async_engine(url).dialect.create_connect_args(sa.engine.make_url(url))[1]


def test_client_timeout_connects_through_the_guarded_class():
    opts = async_connect_args("crate+psycopg://crate@localhost/doc?client_timeout=2.5")
    assert "client_timeout" not in opts
    creator = opts["async_creator_fn"]
    assert creator.func is _psycopg_timeout.connect
    assert creator.keywords["client_timeout"] == 2.5


@pytest.mark.parametrize("value", ["", "0"])
def test_client_timeout_is_off_by_default(value):
    query = f"?client_timeout={value}" if value else ""
    assert "async_creator_fn" not in async_connect_args(f"crate+psycopg://{query}")


@pytest.mark.parametrize("value", ["-1", "soon"])
def test_client_timeout_invalid_values_are_refused(value):
    with pytest.raises(sa.exc.ArgumentError, match="client_timeout"):
        async_connect_args(f"crate+psycopg://?client_timeout={value}")


def test_host_cooldown_skips_marked_hosts():
    cooldown = _psycopg_timeout.HostCooldown()
    opts = {"host": "node1,node2,node3", "port": "5432,5433,", "dbname": "doc"}
    cooldown.mark("node2", 5433)
    assert cooldown.filter(opts) == {"host": "node1,node3", "port": "5432,", "dbname": "doc"}
    cooldown.mark("node3", 5432)
    assert cooldown.filter(opts) == {"host": "node1", "port": "5432", "dbname": "doc"}


def test_host_cooldown_never_leaves_zero_hosts():
    cooldown = _psycopg_timeout.HostCooldown()
    opts = {"host": "node1,node2", "port": "5432"}
    cooldown.mark("node1", 5432)
    cooldown.mark("node2", 5432)
    assert cooldown.filter(opts) is opts
    single = {"host": "node1", "port": 5432}
    assert cooldown.filter(single) is single


def test_host_cooldown_expires(monkeypatch):
    cooldown = _psycopg_timeout.HostCooldown(seconds=30)
    opts = {"host": "node1,node2"}
    cooldown.mark("node1", 5432)
    assert cooldown.filter(opts)["host"] == "node2"
    now = time.monotonic()
    monkeypatch.setattr(_psycopg_timeout.time, "monotonic", lambda: now + 31)
    assert cooldown.filter(opts) is opts


def test_host_cooldown_leaves_mismatched_ports_alone():
    cooldown = _psycopg_timeout.HostCooldown()
    opts = {"host": "node1,node2,node3", "port": "5432,5433"}
    cooldown.mark("node1", 5432)
    assert cooldown.filter(opts) is opts


def test_host_cooldown_host_without_port_matches_any_port():
    cooldown = _psycopg_timeout.HostCooldown()
    cooldown.mark("node1", 5544)
    assert cooldown.filter({"host": "node1,node2"}) == {"host": "node2"}
    assert cooldown.filter({"host": "node1,node2", "port": ","}) == {"host": "node2", "port": ""}


def test_host_cooldown_explicit_ports_match_exactly():
    cooldown = _psycopg_timeout.HostCooldown()
    opts = {"host": "localhost,localhost,localhost", "port": "5432,5433,5434"}
    cooldown.mark("localhost", 5433)
    assert cooldown.filter(opts) == {"host": "localhost,localhost", "port": "5432,5434"}


def test_host_cooldown_filters_hostaddr_in_step():
    """psycopg refuses `host` and `hostaddr` lists of different lengths."""
    cooldown = _psycopg_timeout.HostCooldown()
    opts = {"host": "node1,node2,node3", "hostaddr": "192.0.2.1,192.0.2.2,192.0.2.3"}
    cooldown.mark("node2", 5432)
    assert cooldown.filter(opts) == {"host": "node1,node3", "hostaddr": "192.0.2.1,192.0.2.3"}


def test_host_cooldown_leaves_mismatched_hostaddr_alone():
    cooldown = _psycopg_timeout.HostCooldown()
    opts = {"host": "node1,node2", "hostaddr": "192.0.2.1"}
    cooldown.mark("node1", 5432)
    assert cooldown.filter(opts) is opts


def test_shut_down_socket_keeps_libpq_ownership():
    """The peer sees EOF, and the descriptor stays open for libpq to close."""
    ours, peer = socket.socketpair()
    try:
        connection = types.SimpleNamespace(pgconn=types.SimpleNamespace(socket=ours.fileno()))
        _psycopg_timeout._shut_down_socket(connection)
        assert peer.recv(1) == b""
        assert ours.fileno() != -1
        os.fstat(ours.fileno())
    finally:
        ours.close()
        peer.close()


def test_shut_down_socket_ignores_a_closed_connection():
    class ClosedPGconn:
        @property
        def socket(self):
            raise psycopg.OperationalError("the connection is closed")

    _psycopg_timeout._shut_down_socket(types.SimpleNamespace(pgconn=ClosedPGconn()))


SLOW = "SELECT sum(x) FROM generate_series(1, {bound}) x"


@pytest.fixture
def slow_query(http):
    """
    A statement that runs for many seconds. Its server job is killed afterwards.
    """
    bound = 2_000_000_000 - uuid.uuid4().int % 1_000_000
    marker = f"generate_series(1, {bound})"
    jobs = (
        f"SELECT id FROM sys.jobs WHERE stmt LIKE '%{marker}%' "  # noqa: S608
        "AND stmt NOT LIKE '%sys.jobs%'"
    )

    class SlowQuery:
        statement = sa.text(SLOW.format(bound=bound))

        @staticmethod
        def running():
            return len(http.exec_driver_sql(jobs).fetchall())

    yield SlowQuery
    for (job_id,) in http.exec_driver_sql(jobs).fetchall():
        http.exec_driver_sql(f"KILL '{job_id}'")


@pytest.mark.asyncio
async def test_client_timeout_cuts_a_statement(cratedb_service, slow_query):
    """
    `client_timeout` ends a statement on the client, the pool replaces the
    connection, and the next statement runs on a new one.
    """
    url = sa.engine.make_url(cratedb_service.psycopg_dburi).update_query_dict(
        {"client_timeout": "1"}
    )
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    try:
        started = time.monotonic()
        with pytest.raises(sa.exc.OperationalError, match=r"client_timeout \(1.0 s\) expired") as e:
            async with engine.connect() as connection:
                await connection.execute(slow_query.statement)
        elapsed = time.monotonic() - started
        assert e.value.connection_invalidated
        assert isinstance(e.value.orig, _psycopg_timeout.client_timeout_error())
        assert 1.0 <= elapsed < 2.5

        async with engine.connect() as connection:
            assert (await connection.execute(sa.text("SELECT 42"))).scalar_one() == 42
        # The host is noted, so that a reconnect to a cluster prefers the other hosts.
        assert list(engine.dialect._host_cooldown._until) == [(url.host, str(url.port))]
    finally:
        started = time.monotonic()
        await engine.dispose()
        assert time.monotonic() - started < 1.0


@pytest.mark.asyncio
async def test_client_timeout_lets_fast_statements_pass(cratedb_service):
    url = sa.engine.make_url(cratedb_service.psycopg_dburi).update_query_dict(
        {"client_timeout": "5"}
    )
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            for _ in range(3):
                assert (await connection.execute(sa.text("SELECT 1"))).scalar_one() == 1
    finally:
        await engine.dispose()
    assert engine.dialect._host_cooldown._until == {}


@pytest.mark.asyncio
async def test_without_client_timeout_nothing_is_cut(engine, slow_query):
    async with engine.connect() as connection:
        raw = await connection.get_raw_connection()
        # psycopg's own class: the dialect only replaces it when a timeout is set.
        assert type(raw.driver_connection) is psycopg.AsyncConnection
        task = asyncio.ensure_future(connection.execute(slow_query.statement))
        await asyncio.sleep(2.0)
        assert not task.done()
        assert slow_query.running() == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert engine.dialect._host_cooldown._until == {}


@pytest.mark.asyncio
async def test_cancelled_task_raises_cancelled_error_and_stops_the_job(engine, slow_query):
    """
    Cancelling the task ends the statement on the server. CrateDB reports the
    cancellation with SQLSTATE XX000 instead of 57014; psycopg handles that from
    3.3.9 on by closing the connection.
    """

    async def slow():
        async with engine.connect() as connection:
            await connection.execute(slow_query.statement)

    task = asyncio.create_task(slow())
    await asyncio.sleep(1.5)
    assert slow_query.running() == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(1.0)
    assert slow_query.running() == 0
    async with engine.connect() as connection:
        assert (await connection.execute(sa.text("SELECT 42"))).scalar_one() == 42


@pytest.mark.asyncio
async def test_asyncio_timeout_raises_timeout_error(engine, slow_query):
    async def slow():
        async with engine.connect() as connection:
            await connection.execute(slow_query.statement)

    with pytest.raises(asyncio.TimeoutError):
        if hasattr(asyncio, "timeout"):
            async with asyncio.timeout(1.0):
                await slow()
        else:
            await asyncio.wait_for(slow(), timeout=1.0)
    async with engine.connect() as connection:
        assert (await connection.execute(sa.text("SELECT 42"))).scalar_one() == 42
