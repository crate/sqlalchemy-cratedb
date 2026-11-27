"""
The psycopg dialect, asyncio: `create_async_engine("crate+psycopg://...")`.
"""

import asyncio
import datetime as dt
import decimal
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

from sqlalchemy_cratedb import Geopoint, ObjectType  # noqa: E402
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


@pytest.fixture
def batch_table(http):
    http.exec_driver_sql("DROP TABLE IF EXISTS psycopg_async_batch")
    http.exec_driver_sql(
        "CREATE TABLE psycopg_async_batch (id INT PRIMARY KEY, value INT CHECK (value >= 0))"
    )
    yield "psycopg_async_batch"
    http.exec_driver_sql("DROP TABLE IF EXISTS psycopg_async_batch")


@pytest.mark.asyncio
@pytest.mark.parametrize("executemany_mode", ["bulk", "loop"])
async def test_executemany_matches_sync(cratedb_service, http, batch_table, executemany_mode):
    """
    The async dialect reports each row of a batch as the sync one does, and a
    value that does not cast raises instead of hanging.
    """
    insert = sa.text("INSERT INTO psycopg_async_batch (id, value) VALUES (:id, :value)")
    batches = [
        (insert, [{"id": 3, "value": 30}, {"id": 1, "value": 99}, {"id": 4, "value": 40}]),
        (
            sa.text("UPDATE psycopg_async_batch SET value = :value WHERE id = :id"),
            [{"id": 0, "value": 5}, {"id": 1, "value": -1}, {"id": 99, "value": 1}],
        ),
        (
            sa.text("UPDATE psycopg_async_batch SET value = :value WHERE id = :id"),
            [{"id": 0, "value": 5}, {"id": 1, "value": "abc"}, {"id": 2, "value": 25}],
        ),
    ]

    def reset():
        http.exec_driver_sql("DELETE FROM psycopg_async_batch")
        http.exec_driver_sql(
            "INSERT INTO psycopg_async_batch (id, value) VALUES (0, 0), (1, 10), (2, 20)"
        )
        http.exec_driver_sql("REFRESH TABLE psycopg_async_batch")

    def stored():
        http.exec_driver_sql("REFRESH TABLE psycopg_async_batch")
        return http.exec_driver_sql("SELECT * FROM psycopg_async_batch ORDER BY id").all()

    def outcome(connection, statement, parameters):
        try:
            result = connection.execute(statement, parameters)
        except sa.exc.DBAPIError as e:
            return type(e)
        return [row["rowcount"] for row in result.context.last_result], result.rowcount

    sync_engine = sa.create_engine(cratedb_service.psycopg_dburi, executemany_mode=executemany_mode)
    async_engine = create_async_engine(
        cratedb_service.psycopg_dburi, executemany_mode=executemany_mode
    )
    try:
        for statement, parameters in batches:
            reset()
            with sync_engine.connect() as connection:
                expected = outcome(connection, statement, parameters), stored()
            reset()
            async with async_engine.connect() as connection:
                try:
                    result = await asyncio.wait_for(connection.execute(statement, parameters), 30)
                except sa.exc.DBAPIError as e:
                    actual = type(e)
                else:
                    actual = (
                        [row["rowcount"] for row in result.context.last_result],
                        result.rowcount,
                    )
                assert (await connection.execute(sa.text("SELECT 1"))).scalar_one() == 1
            assert (actual, stored()) == expected
    finally:
        sync_engine.dispose()
        await async_engine.dispose()


@pytest.mark.asyncio
async def test_executemany_marks_a_failed_row(engine, http, batch_table):
    http.exec_driver_sql(
        "INSERT INTO psycopg_async_batch (id, value) VALUES (0, 0), (1, 10), (2, 20)"
    )
    http.exec_driver_sql("REFRESH TABLE psycopg_async_batch")
    async with engine.connect() as connection:
        result = await connection.execute(
            sa.text("UPDATE psycopg_async_batch SET value = :value WHERE id = :id"),
            [{"id": 0, "value": 5}, {"id": 1, "value": -1}, {"id": 2, "value": 25}],
        )
    assert [row["rowcount"] for row in result.context.last_result] == [1, -2, 1]
    assert result.rowcount == 2


@pytest.mark.asyncio
async def test_insert_bulk_via_run_sync(engine, http):
    pd = pytest.importorskip("pandas")
    from sqlalchemy_cratedb import insert_bulk

    df = pd.DataFrame({"id": range(100), "name": [f"n{i}" for i in range(100)]})

    def to_sql(connection):
        df.to_sql(
            "psycopg_async_bulk",
            con=connection,
            index=False,
            if_exists="replace",
            chunksize=30,
            method=insert_bulk,
        )

    try:
        async with engine.connect() as connection:
            await connection.run_sync(to_sql)
        http.exec_driver_sql("REFRESH TABLE psycopg_async_bulk")
        rows = http.exec_driver_sql("SELECT count(*), max(name) FROM psycopg_async_bulk").one()
        assert rows == (100, "n99")
    finally:
        http.exec_driver_sql("DROP TABLE IF EXISTS psycopg_async_bulk")


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
