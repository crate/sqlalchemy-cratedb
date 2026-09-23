import uuid

import pytest
import sqlalchemy as sa

from sqlalchemy_cratedb.dialect import CrateDialect
from sqlalchemy_cratedb.sa_version import SA_2_0, SA_VERSION

pytestmark = pytest.mark.skipif(SA_VERSION < SA_2_0, reason="SQLAlchemy 1.4 has no UUID type")

VALUE = uuid.UUID("5f0b6b4e-6d2a-4a55-9b0e-1c9a3f2d7e41")


def bind(type_, value):
    dialect = CrateDialect()
    return type_.dialect_impl(dialect).bind_processor(dialect)(value)


def render(type_):
    return CrateDialect().type_compiler.process(type_)


@pytest.fixture
def engine(cratedb_service):
    engine = cratedb_service.database.engine
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS uuids")
    return engine


def test_native_uuid_renders_crate_uuid_and_portable_uuid_keeps_char():
    assert render(sa.UUID()) == "UUID"
    assert render(sa.Uuid()) == "CHAR(32)"


@pytest.mark.parametrize("value", [VALUE, str(VALUE), VALUE.hex], ids=["UUID", "dashed", "hex"])
def test_native_uuid_binds_the_dashed_form(value):
    assert bind(sa.UUID(as_uuid=not isinstance(value, str)), value) == str(VALUE)


def test_portable_uuid_binds_the_hex_form():
    assert bind(sa.Uuid(), VALUE) == VALUE.hex


def test_native_uuid_literal_is_dashed():
    statement = sa.select(sa.literal(VALUE, sa.UUID()))
    compiled = statement.compile(dialect=CrateDialect(), compile_kwargs={"literal_binds": True})
    assert "'{0}'".format(VALUE) in str(compiled)


@pytest.mark.parametrize("as_uuid", [True, False])
def test_native_uuid_round_trips(engine, as_uuid):
    table = sa.Table(
        "uuids",
        sa.MetaData(),
        sa.Column("id", sa.UUID(as_uuid=as_uuid)),
    )
    value = VALUE if as_uuid else str(VALUE)
    with engine.begin() as connection:
        table.create(connection)
        connection.execute(table.insert().values(id=value))
        connection.exec_driver_sql("REFRESH TABLE uuids")
        assert connection.execute(sa.select(table.c.id)).scalar() == value
        matched = connection.execute(sa.select(table.c.id).where(table.c.id == value)).scalar()
        assert matched == value


def test_reflected_uuid_column_is_native_uuid(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE uuids (id UUID, ids ARRAY(UUID))")
    table = sa.Table("uuids", sa.MetaData(), autoload_with=engine)
    assert isinstance(table.c.id.type, sa.UUID)
    assert isinstance(table.c.ids.type.item_type, sa.UUID)
    with engine.begin() as connection:
        connection.execute(table.insert().values(id=VALUE))
        connection.exec_driver_sql("REFRESH TABLE uuids")
        assert connection.execute(sa.select(table.c.id)).scalar() == VALUE
    ddl = str(sa.schema.CreateTable(table).compile(engine))
    assert "id UUID" in ddl
    assert "ids ARRAY(UUID)" in ddl
