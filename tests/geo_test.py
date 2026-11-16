import geojson
import pytest
import sqlalchemy as sa

from sqlalchemy_cratedb import Geopoint, Geoshape
from sqlalchemy_cratedb.dialect import CrateDialect

POINT = (9.74, 47.41)


def result(type_, value):
    dialect = CrateDialect()
    return type_().result_processor(dialect, None)(value)


@pytest.mark.parametrize("type_", [Geopoint, Geoshape])
def test_null_result_is_none(type_):
    assert result(type_, None) is None


def test_geopoint_result_is_tuple():
    assert result(Geopoint, list(POINT)) == POINT


def test_geoshape_result_is_geojson():
    value = result(Geoshape, {"type": "Point", "coordinates": list(POINT)})
    assert isinstance(value, geojson.Point)
    assert tuple(value.coordinates) == POINT


@pytest.fixture
def places(cratedb_service):
    table = sa.Table(
        "places",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("p", Geopoint),
        sa.Column("s", Geoshape),
    )
    engine = cratedb_service.engine
    with engine.begin() as connection:
        table.drop(connection, checkfirst=True)
        table.create(connection)
        connection.execute(
            table.insert(),
            [
                {"id": 1, "p": None, "s": None},
                {"id": 2, "p": list(POINT), "s": geojson.Point(list(POINT))},
            ],
        )
    cratedb_service.refresh_table("places")
    yield engine, table
    with engine.begin() as connection:
        table.drop(connection)


def test_null_geo_values_read_as_none(places):
    engine, table = places
    with engine.connect() as connection:
        row = connection.execute(sa.select(table.c.p, table.c.s).where(table.c.id == 1)).one()
    assert row.p is None
    assert row.s is None


def test_geo_values_round_trip(places):
    engine, table = places
    with engine.connect() as connection:
        row = connection.execute(sa.select(table.c.p, table.c.s).where(table.c.id == 2)).one()
    assert row.p == POINT
    assert isinstance(row.s, geojson.Point)
    assert tuple(row.s.coordinates) == POINT
