import sqlalchemy as sa

from tests.conftest import TESTDRIVE_DATA_SCHEMA


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
