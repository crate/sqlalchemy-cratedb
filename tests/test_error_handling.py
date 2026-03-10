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
            connection.execute(sa.text("CREATE TABLE foo AS SELECT 1 AS _id"))

        # Make sure both variants match, to validate it's actually an error trace.
        assert ex.match(re.escape('InvalidColumnNameException["_id" conflicts with system column]'))
        assert ex.match(
            'io.crate.exceptions.InvalidColumnNameException: "_id" conflicts with system column'
        )
