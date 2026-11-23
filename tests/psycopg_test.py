import datetime as dt
import decimal
import importlib
import subprocess
import sys
import uuid

import pytest
import sqlalchemy as sa
from verlib2 import Version

from sqlalchemy_cratedb.sa_version import SA_VERSION

if SA_VERSION < Version("2.0.44"):
    pytest.skip("The psycopg dialect requires SQLAlchemy 2.0.44", allow_module_level=True)

psycopg = pytest.importorskip("psycopg")

from sqlalchemy_cratedb import Geopoint, ObjectArray, ObjectType  # noqa: E402
from sqlalchemy_cratedb.dialect_psycopg import (  # noqa: E402
    CrateDialect_psycopg,
    CrateDialectAsync_psycopg,
)


@pytest.fixture
def engine(cratedb_service):
    engine = sa.create_engine(cratedb_service.psycopg_dburi)
    yield engine
    engine.dispose()


@pytest.fixture
def http(cratedb_service):
    """
    A `crate://` connection, the reference for values and reflection.
    """
    engine = sa.create_engine(cratedb_service.http_dburi)
    with engine.connect() as connection:
        yield connection
    engine.dispose()


def connect_args(url):
    return sa.create_engine(url).dialect.create_connect_args(sa.engine.make_url(url))[1]


def test_url_selects_the_psycopg_dialect():
    engine = sa.create_engine("crate+psycopg://")
    assert type(engine.dialect) is CrateDialect_psycopg
    assert engine.dialect.name == "crate"
    assert engine.dialect.driver == "psycopg"
    assert engine.dialect.paramstyle == "pyformat"
    assert not engine.dialect.is_async


def test_http_url_does_not_import_psycopg():
    code = (
        "import sys, sqlalchemy as sa; "
        "engine = sa.create_engine('crate://'); "
        "assert type(engine.dialect).__name__ == 'CrateDialect'; "
        "assert 'sqlalchemy_cratedb.dialect_psycopg' not in sys.modules; "
        "assert 'psycopg' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603


def test_connect_args_defaults():
    assert connect_args("crate+psycopg://") == {
        "user": "crate",
        "dbname": "doc",
        "autocommit": True,
        "prepare_threshold": None,
        "connect_timeout": 10,
    }


def test_connect_args_from_url():
    opts = connect_args(
        "crate+psycopg://admin:secret@cratedb.example.org:5433/sensors"
        "?connect_timeout=3&prepare_threshold=5&sslmode=require&autocommit=false"
    )
    assert opts == {
        "host": "cratedb.example.org",
        "port": 5433,
        "user": "admin",
        "password": "secret",
        "dbname": "sensors",
        "connect_timeout": "3",
        "prepare_threshold": 5,
        "sslmode": "require",
        "autocommit": True,
    }


@pytest.mark.parametrize(
    "query, hosts, ports",
    [
        ("host=node1:5433&host=node2:5434&host=node3", "node1,node2,node3", "5433,5434,"),
        ("host=node1,node2&port=5433,5434", "node1,node2", "5433,5434"),
        ("host=node1&host=node2", "node1,node2", None),
    ],
)
def test_connect_args_several_hosts(query, hosts, ports):
    opts = connect_args(f"crate+psycopg://crate@/doc?{query}")
    assert opts["host"] == hosts
    assert opts.get("port") == ports


def test_connect_args_schema_is_not_sent_to_psycopg():
    assert "schema" not in connect_args("crate+psycopg://crate@localhost/doc?schema=sensors")


@pytest.mark.parametrize("sslmode", ["verify-ca", "verify-full"])
def test_connect_args_certificate_checks_use_certifi(sslmode):
    certifi = pytest.importorskip("certifi")
    url = f"crate+psycopg://crate@localhost/doc?sslmode={sslmode}"
    assert connect_args(url)["sslrootcert"] == certifi.where()
    assert connect_args(f"{url}&sslrootcert=/etc/ssl/cratedb-ca.pem")["sslrootcert"] == (
        "/etc/ssl/cratedb-ca.pem"
    )


def test_connect_args_certifi_only_for_certificate_checks():
    assert "sslrootcert" not in connect_args("crate+psycopg://crate@localhost/doc?sslmode=require")


@pytest.mark.parametrize("dialect_cls", [CrateDialect_psycopg, CrateDialectAsync_psycopg])
def test_statement_cache_declared_on_each_class(dialect_cls):
    """
    SQLAlchemy reads the flag from the class itself, not from its bases.
    """
    assert dialect_cls.__dict__["supports_statement_cache"] is True


@pytest.mark.parametrize("dialect_cls", [CrateDialect_psycopg, CrateDialectAsync_psycopg])
def test_psycopg_below_minimum_version_is_refused(monkeypatch, dialect_cls):
    monkeypatch.setattr(psycopg, "__version__", "3.3.8")
    with pytest.raises(ImportError, match=r"requires psycopg>=3\.3\.9, found 3\.3\.8"):
        dialect_cls.import_dbapi()


def test_sqlalchemy_below_minimum_version_is_refused(monkeypatch):
    monkeypatch.setattr("sqlalchemy_cratedb.sa_version.SA_VERSION", Version("2.0.43"))
    monkeypatch.delitem(sys.modules, "sqlalchemy_cratedb.dialect_psycopg")
    with pytest.raises(ImportError, match=r"requires SQLAlchemy>=2\.0\.44"):
        importlib.import_module("sqlalchemy_cratedb.dialect_psycopg")


def test_ddl_is_cratedb_ddl():
    table = sa.Table(
        "sensor_readings",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("payload", ObjectType),
        crate_number_of_shards=3,
    )
    ddl = str(sa.schema.CreateTable(table).compile(dialect=CrateDialect_psycopg()))
    assert "payload OBJECT" in ddl
    assert "CLUSTERED INTO 3 SHARDS" in ddl


def test_initialize(engine, http):
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT 1")).scalar_one() == 1
        driver_connection = connection.connection.driver_connection
        assert isinstance(driver_connection, psycopg.Connection)
        assert driver_connection.autocommit
    assert engine.dialect.default_schema_name == "doc"
    assert engine.dialect.server_version_info == http.dialect.server_version_info


def test_default_schema_is_the_database_name(cratedb_service, http):
    url = sa.engine.make_url(cratedb_service.psycopg_dburi).set(database="sensors")
    engine = sa.create_engine(url)
    table = sa.Table("readings", sa.MetaData(), sa.Column("id", sa.Integer))
    try:
        table.create(engine)
        assert engine.dialect.default_schema_name == "sensors"
        assert "readings" in sa.inspect(http).get_table_names(schema="sensors")
    finally:
        table.drop(engine, checkfirst=True)
        engine.dispose()


def test_user_without_privileges(engine, cratedb_service):
    """
    A new user cannot read `sys.nodes`. Connecting must not depend on it.
    """
    with engine.connect() as connection:
        connection.execute(sa.text("CREATE USER sensor_reader"))
    url = sa.engine.make_url(cratedb_service.psycopg_dburi).set(username="sensor_reader")
    reader = sa.create_engine(url)
    try:
        with reader.connect() as connection:
            assert connection.execute(sa.text("SELECT 1")).scalar_one() == 1
        assert reader.dialect.server_version_info == engine.dialect.server_version_info
        assert reader.dialect.default_schema_name == "doc"
    finally:
        reader.dispose()
        with engine.connect() as connection:
            connection.execute(sa.text("DROP USER sensor_reader"))


def test_connection_from_creator_runs_in_autocommit(cratedb_service):
    url = sa.engine.make_url(cratedb_service.psycopg_dburi)

    def creator():
        return psycopg.connect(host=url.host, port=url.port, user="crate", dbname="doc")

    engine = sa.create_engine(url, creator=creator)
    try:
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
            driver_connection = connection.connection.driver_connection
            assert driver_connection.autocommit
            assert driver_connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
    finally:
        engine.dispose()


def test_other_isolation_levels_are_refused(cratedb_service):
    engine = sa.create_engine(cratedb_service.psycopg_dburi, isolation_level="REPEATABLE READ")
    try:
        with pytest.raises(sa.exc.ArgumentError, match="Valid isolation levels .* AUTOCOMMIT"):
            engine.connect()
    finally:
        engine.dispose()


def test_unreachable_server():
    engine = sa.create_engine("crate+psycopg://crate@localhost:1/doc?connect_timeout=2")
    with pytest.raises(sa.exc.OperationalError):
        engine.connect()


def test_pool_pre_ping_replaces_a_closed_connection(cratedb_service):
    engine = sa.create_engine(
        cratedb_service.psycopg_dburi, pool_pre_ping=True, pool_size=1, max_overflow=0
    )
    try:
        with engine.connect() as connection:
            first = connection.connection.driver_connection
            first.close()
        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT 1")).scalar_one() == 1
            assert connection.connection.driver_connection is not first
    finally:
        engine.dispose()


def test_ddl_repeated_on_a_recreated_table(engine):
    """
    psycopg prepares a statement from its fifth run. A prepared `DROP TABLE`
    fails once the table has been recreated.
    """
    table = sa.Table("recreated_readings", sa.MetaData(), sa.Column("id", sa.Integer))
    for _ in range(7):
        table.create(engine)
        table.drop(engine)


def test_values_match_http(engine, http):
    metadata = sa.MetaData()
    table = sa.Table(
        "psycopg_values",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("day", sa.Date),
        sa.Column("measured_at", sa.DateTime),
        sa.Column("measured_at_tz", sa.DateTime(timezone=True)),
        sa.Column("price", sa.Numeric(10, 2)),
        sa.Column("temperature", sa.Float),
        sa.Column("active", sa.Boolean),
        sa.Column("device_id", sa.Uuid),
        sa.Column("device_name", sa.Uuid(as_uuid=False)),
        sa.Column("tags", sa.ARRAY(sa.String)),
        sa.Column("payload", ObjectType),
        sa.Column("events", ObjectArray),
        sa.Column("location", Geopoint),
    )
    row = {
        "id": 1,
        "day": dt.date(2026, 10, 26),
        "measured_at": dt.datetime(2026, 10, 26, 12, 30, 1, 123000),
        "measured_at_tz": dt.datetime(
            2026, 10, 26, 23, 30, tzinfo=dt.timezone(dt.timedelta(hours=-2))
        ),
        "price": decimal.Decimal("1.50"),
        "temperature": 21.25,
        "active": True,
        "device_id": uuid.UUID("6f0c7b6e-6a3e-4e53-8c0b-0d6c7a1b2c3d"),
        "device_name": "0b6c4d5e-8f9a-4b1c-9d2e-3f4a5b6c7d8e",
        "tags": ["indoor", "calibrated"],
        "payload": {"unit": "celsius", "calibration": {"offset": 0.5}, "history": [20, 21]},
        "events": [{"kind": "reboot", "codes": [3, 7]}, {"kind": "update"}],
        "location": (10.95667, 47.18917),
    }
    nulls = dict.fromkeys(row) | {"id": 2}
    with engine.connect() as connection:
        metadata.drop_all(connection, checkfirst=True)
        metadata.create_all(connection)
        connection.execute(table.insert(), [row, nulls])
        connection.execute(sa.text("REFRESH TABLE psycopg_values"))
        ours = connection.execute(sa.select(table).order_by(table.c.id)).all()
    try:
        theirs = http.execute(sa.select(table).order_by(table.c.id)).all()
        assert len(ours) == len(theirs) == 2
        for our_row, their_row in zip(ours, theirs):
            for key in row:
                our_value, their_value = getattr(our_row, key), getattr(their_row, key)
                assert type(our_value) is type(their_value), key
                if key == "location" and their_value is not None:
                    their_value = pytest.approx(their_value)
                assert our_value == their_value, key
        assert ours[0].day == row["day"]
        assert ours[0].measured_at == row["measured_at"]
        assert ours[0].measured_at_tz == dt.datetime(2026, 10, 27, 1, 30)
        assert ours[0].device_id == row["device_id"]
        assert ours[0].device_name == row["device_name"]
        assert ours[0].payload == row["payload"]
        assert ours[0].events == row["events"]
        assert tuple(ours[1]) == (2,) + (None,) * (len(row) - 1)
    finally:
        metadata.drop_all(http)


def test_native_uuid_values_match_http(engine, http):
    if http.dialect.server_version_info < (6, 2):
        pytest.skip("CrateDB < 6.2 has no UUID type")
    metadata = sa.MetaData()
    table = sa.Table(
        "psycopg_uuids",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("firmware_id", sa.UUID),
        sa.Column("firmware_name", sa.UUID(as_uuid=False)),
    )
    row = {
        "id": 1,
        "firmware_id": uuid.UUID("3d2c1b0a-9f8e-4d7c-8b6a-5f4e3d2c1b0a"),
        "firmware_name": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    }
    with engine.connect() as connection:
        metadata.drop_all(connection, checkfirst=True)
        metadata.create_all(connection)
        connection.execute(
            table.insert(), [row, {"id": 2, "firmware_id": None, "firmware_name": None}]
        )
        connection.execute(sa.text("REFRESH TABLE psycopg_uuids"))
        ours = connection.execute(sa.select(table).order_by(table.c.id)).all()
    try:
        theirs = http.execute(sa.select(table).order_by(table.c.id)).all()
        assert ours == theirs
        assert [type(value) for value in ours[0]] == [type(value) for value in theirs[0]]
        assert tuple(ours[0]) == tuple(row.values())
        assert tuple(ours[1]) == (2, None, None)
    finally:
        metadata.drop_all(http)


def test_numeric_keeps_precision(engine):
    """
    psycopg returns `NUMERIC` as an exact `Decimal`.
    """
    metadata = sa.MetaData()
    table = sa.Table(
        "psycopg_balances",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("balance", sa.Numeric(20, 2)),
        sa.Column("balance_float", sa.Numeric(20, 2, asdecimal=False)),
    )
    balance = decimal.Decimal("9007199254740993.25")
    with engine.connect() as connection:
        metadata.drop_all(connection, checkfirst=True)
        metadata.create_all(connection)
        try:
            connection.execute(
                table.insert(), {"id": 1, "balance": balance, "balance_float": balance}
            )
            connection.execute(sa.text("REFRESH TABLE psycopg_balances"))
            row = connection.execute(sa.select(table.c.balance, table.c.balance_float)).one()
            assert row.balance == balance
            assert type(row.balance_float) is float
            assert row.balance_float == float(balance)
        finally:
            metadata.drop_all(connection)


@pytest.fixture
def readings(http):
    http.exec_driver_sql("DROP TABLE IF EXISTS psycopg_readings")
    http.exec_driver_sql(
        "CREATE TABLE psycopg_readings (id INT PRIMARY KEY, value INT CHECK (value >= 0))"
    )
    yield sa.table("psycopg_readings", sa.column("id"), sa.column("value"))
    http.exec_driver_sql("DROP TABLE IF EXISTS psycopg_readings")


def test_sql_errors(engine, readings):
    """
    CrateDB reports a CHECK violation with the generic SQLSTATE XX000, as many
    other errors. `crate://` raises `ProgrammingError` for those.
    """
    with engine.connect() as connection:
        with pytest.raises(sa.exc.ProgrammingError, match=r"CHECK \(\"value\" >= 0\)") as excinfo:
            connection.execute(sa.insert(readings), {"id": 1, "value": -1})
        assert excinfo.value.orig.sqlstate == "XX000"
        with pytest.raises(sa.exc.ProgrammingError):
            connection.execute(sa.text("SELECT * FROM unknown_readings"))
        assert connection.execute(sa.text("SELECT 2")).scalar_one() == 2


def test_executemany_runs_one_statement_per_row(engine, http, readings):
    with engine.connect() as connection:
        connection.execute(sa.insert(readings), [{"id": i, "value": i * 10} for i in range(5)])
        connection.execute(sa.text("REFRESH TABLE psycopg_readings"))

        update = sa.update(readings).where(readings.c.id == sa.bindparam("b_id"))
        update = update.values(value=sa.bindparam("b_value"))
        result = connection.execute(
            update,
            [{"b_id": 1, "b_value": 15}, {"b_id": 99, "b_value": 0}, {"b_id": 2, "b_value": 25}],
        )
        assert result.rowcount == 2

        with pytest.raises(sa.exc.ProgrammingError, match=r"CHECK \(\"value\" >= 0\)"):
            connection.execute(
                update,
                [{"b_id": 3, "b_value": 35}, {"b_id": 4, "b_value": -1}, {"b_id": 0, "b_value": 5}],
            )
    http.exec_driver_sql("REFRESH TABLE psycopg_readings")
    values = http.exec_driver_sql("SELECT id, value FROM psycopg_readings ORDER BY id").all()
    # The rows before the failed one are written, the rows after it are not sent.
    assert values == [(0, 0), (1, 15), (2, 25), (3, 35), (4, 40)]


def test_reflection_matches_http(engine, http):
    metadata = sa.MetaData()
    sa.Table(
        "psycopg_reflection",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String),
        sa.Column("payload", ObjectType),
    )
    with engine.connect() as connection:
        metadata.drop_all(connection, checkfirst=True)
        metadata.create_all(connection)
        connection.execute(
            sa.text("CREATE VIEW psycopg_reflection_view AS SELECT id FROM psycopg_reflection")
        )
        try:
            ours, theirs = sa.inspect(connection), sa.inspect(http)
            assert "psycopg_reflection" in ours.get_table_names()
            assert ours.get_table_names() == theirs.get_table_names()
            assert ours.get_view_names() == theirs.get_view_names() == ["psycopg_reflection_view"]
            assert str(ours.get_columns("psycopg_reflection")) == str(
                theirs.get_columns("psycopg_reflection")
            )
            assert ours.get_pk_constraint("psycopg_reflection") == {
                "constrained_columns": ["id"],
                "name": "PRIMARY KEY",
            }
            assert ours.get_schema_names() == theirs.get_schema_names()
            assert ours.has_table("psycopg_reflection")
        finally:
            connection.execute(sa.text("DROP VIEW psycopg_reflection_view"))
            metadata.drop_all(connection)


def test_schema_from_url_query(cratedb_service):
    url = sa.engine.make_url(cratedb_service.psycopg_dburi).update_query_dict({"schema": "sys"})
    engine = sa.create_engine(url)
    try:
        with engine.connect() as connection:
            assert "nodes" in sa.inspect(connection).get_table_names()
    finally:
        engine.dispose()


def test_orm_object_partial_update(engine, http):
    """
    A change to one key of an `ObjectType` is written as `payload['key'] = ...`,
    as on `crate://`. A deleted key becomes null.
    """
    from sqlalchemy.orm import Session, declarative_base

    Base = declarative_base()

    class Device(Base):
        __tablename__ = "psycopg_devices"
        id = sa.Column(sa.Integer, primary_key=True)
        payload = sa.Column(ObjectType)

    Base.metadata.drop_all(engine, checkfirst=True)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(Device(id=1, payload={"firmware": "1.0", "room": "lab"}))
            session.commit()
            session.execute(sa.text("REFRESH TABLE psycopg_devices"))
            device = session.get(Device, 1)
            device.payload["firmware"] = "1.1"
            del device.payload["room"]
            session.commit()
        http.exec_driver_sql("REFRESH TABLE psycopg_devices")
        stored = http.exec_driver_sql("SELECT payload FROM psycopg_devices").scalar()
        assert stored == {"firmware": "1.1", "room": None}
    finally:
        Base.metadata.drop_all(http)
