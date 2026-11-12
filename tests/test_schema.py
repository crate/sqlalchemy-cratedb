import sqlalchemy as sa

from tests.conftest import TESTDRIVE_DATA_SCHEMA, TESTDRIVE_EXT_SCHEMA


def test_correct_schema(cratedb_service):
    """
    Tests that the correct schema is being picked up.
    """
    tablename = f'"{TESTDRIVE_DATA_SCHEMA}"."foobar"'
    cratedb_service.run_sql(f"DROP TABLE IF EXISTS {tablename}")
    cratedb_service.run_sql(f"CREATE TABLE {tablename} AS SELECT 1")

    inspector: sa.Inspector = sa.inspect(cratedb_service.engine)
    assert TESTDRIVE_DATA_SCHEMA in inspector.get_schema_names()

    table_names = inspector.get_table_names(schema=TESTDRIVE_DATA_SCHEMA)
    assert table_names == ["foobar"]

    view_names = inspector.get_view_names(schema=TESTDRIVE_DATA_SCHEMA)
    assert view_names == []

    indexes = inspector.get_indexes(tablename)
    assert indexes == []


def test_get_view_names_filters_by_schema(cratedb_service):
    """
    Tests that `get_view_names()` only lists the views of the requested schema.
    """
    view_data = f'"{TESTDRIVE_DATA_SCHEMA}"."view_data"'
    view_ext = f'"{TESTDRIVE_EXT_SCHEMA}"."view_ext"'
    cratedb_service.run_sql(f"CREATE OR REPLACE VIEW {view_data} AS SELECT 1 AS x")
    cratedb_service.run_sql(f"CREATE OR REPLACE VIEW {view_ext} AS SELECT 2 AS x")
    try:
        inspector: sa.Inspector = sa.inspect(cratedb_service.engine)
        assert inspector.get_view_names(schema=TESTDRIVE_DATA_SCHEMA) == ["view_data"]
        assert inspector.get_view_names(schema=TESTDRIVE_EXT_SCHEMA) == ["view_ext"]
        assert inspector.get_view_names() == []

        metadata = sa.MetaData()
        metadata.reflect(cratedb_service.engine, schema=TESTDRIVE_DATA_SCHEMA, views=True)
        assert f"{TESTDRIVE_DATA_SCHEMA}.view_data" in metadata.tables
        assert f"{TESTDRIVE_EXT_SCHEMA}.view_ext" not in metadata.tables
    finally:
        cratedb_service.run_sql(f"DROP VIEW IF EXISTS {view_data}")
        cratedb_service.run_sql(f"DROP VIEW IF EXISTS {view_ext}")
