import re
import sys

import pytest
from pueblo.testing.pandas import makeTimeDataFrame
from sqlalchemy.exc import ProgrammingError

from sqlalchemy_cratedb.sa_version import SA_2_0, SA_VERSION
from sqlalchemy_cratedb.support.pandas import table_kwargs

TABLE_NAME = "foobar"
INSERT_RECORDS = 42

# Create dataframe, to be used as input data.
df = makeTimeDataFrame(nper=INSERT_RECORDS, freq="S")
df["time"] = df.index


@pytest.mark.skipif(
    sys.version_info < (3, 8), reason="Feature not supported on Python 3.7 and earlier"
)
@pytest.mark.skipif(
    SA_VERSION < SA_2_0, reason="Feature not supported on SQLAlchemy 1.4 and earlier"
)
def test_table_kwargs_partitioned_by(cratedb_service):
    """
    Validate adding CrateDB dialect table option `PARTITIONED BY` at runtime.
    """

    engine = cratedb_service.database.engine

    # Insert records from pandas dataframe.
    with table_kwargs(crate_partitioned_by="time"):
        df.to_sql(
            TABLE_NAME,
            engine,
            if_exists="replace",
            index=False,
        )

    # Synchronize writes.
    cratedb_service.database.refresh_table(TABLE_NAME)

    # Inquire table cardinality.
    count = cratedb_service.database.count_records(TABLE_NAME)

    # Compare outcome.
    assert count == INSERT_RECORDS

    # Validate SQL DDL.
    ddl = cratedb_service.database.run_sql(f"SHOW CREATE TABLE {TABLE_NAME}")
    assert 'PARTITIONED BY ("time")' in ddl[0][0]


@pytest.mark.skipif(
    sys.version_info < (3, 8), reason="Feature not supported on Python 3.7 and earlier"
)
@pytest.mark.skipif(
    SA_VERSION < SA_2_0, reason="Feature not supported on SQLAlchemy 1.4 and earlier"
)
def test_table_kwargs_translog_durability(cratedb_service):
    """
    Validate adding CrateDB dialect table option `translog.durability` at runtime.
    """

    engine = cratedb_service.database.engine

    # Insert records from pandas dataframe.
    with table_kwargs(**{'crate_"translog.durability"': "'async'"}):
        df.to_sql(
            TABLE_NAME,
            engine,
            if_exists="replace",
            index=False,
        )

    # Synchronize writes.
    cratedb_service.database.refresh_table(TABLE_NAME)

    # Inquire table cardinality.
    count = cratedb_service.database.count_records(TABLE_NAME)

    # Compare outcome.
    assert count == INSERT_RECORDS

    # Validate SQL DDL.
    ddl = cratedb_service.database.run_sql(f"SHOW CREATE TABLE {TABLE_NAME}")
    assert """"translog.durability" = 'ASYNC'""" in ddl[0][0]


@pytest.mark.skipif(
    sys.version_info < (3, 8), reason="Feature not supported on Python 3.7 and earlier"
)
@pytest.mark.skipif(
    SA_VERSION < SA_2_0, reason="Feature not supported on SQLAlchemy 1.4 and earlier"
)
def test_table_kwargs_unknown(cratedb_service):
    """
    Validate behaviour when adding an unknown CrateDB dialect table option.
    """
    engine = cratedb_service.database.engine
    with table_kwargs(crate_unknown_option="'bazqux'"):
        with pytest.raises(ProgrammingError) as ex:
            df.to_sql(
                TABLE_NAME,
                engine,
                if_exists="replace",
                index=False,
            )
        assert ex.match(
            re.escape(
                'SQLParseException[Invalid property "unknown_option" '
                "passed to [ALTER | CREATE] TABLE statement]"
            )
        )
