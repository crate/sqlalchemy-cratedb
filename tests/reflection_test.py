import sqlalchemy as sa


def test_get_columns_nullable_live(cratedb_service):
    """
    Primary key and `NOT NULL` columns reflect as not nullable on a real server,
    whichever type the server reports `information_schema.columns.is_nullable` as.
    """
    engine = cratedb_service.database.engine
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS testdrive.nullable_reflection")
        conn.exec_driver_sql(
            "CREATE TABLE testdrive.nullable_reflection "
            "(id INT PRIMARY KEY, code INT NOT NULL, x TEXT)"
        )
    try:
        columns = sa.inspect(engine).get_columns("nullable_reflection", schema="testdrive")
        assert [(c["name"], c["nullable"]) for c in columns] == [
            ("id", False),
            ("code", False),
            ("x", True),
        ]
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS testdrive.nullable_reflection")
