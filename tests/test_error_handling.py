import re

import pytest
import sqlalchemy as sa


def test_statement_with_error_trace(cratedb_service):
    """
    Verify that the `error_trace` option works correctly.
    """
    engine = sa.create_engine(cratedb_service.database.dburi, connect_args={"error_trace": True})
    with engine.connect() as connection:
        with pytest.raises(sa.exc.ProgrammingError) as ex:
            connection.execute(sa.text("CREATE TABLE foo AS SELECT 1 AS _foo"))
        assert ex.match(
            re.escape('InvalidColumnNameException["_foo" conflicts with system column pattern]')
        )
        assert ex.match(
            "io.crate.exceptions.InvalidColumnNameException: "
            '"_foo" conflicts with system column pattern'
        )
