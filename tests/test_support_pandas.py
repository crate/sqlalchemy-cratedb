import re
import sys

import pandas as pd
import pytest
import sqlalchemy as sa
from pandas._testing import assert_equal
from pueblo.testing.pandas import makeTimeDataFrame
from sqlalchemy.exc import ProgrammingError

from sqlalchemy_cratedb.sa_version import SA_2_0, SA_VERSION
from sqlalchemy_cratedb.support.pandas import table_kwargs

TABLE_NAME = "foobar"
INSERT_RECORDS = 42

# Create dataframe, to be used as input data.
df = makeTimeDataFrame(nper=INSERT_RECORDS, freq="S")
df["time"] = df.index

float_double_data = {
    "col_1": [19556.88, 629414.27, 51570.0, 2933.52, 20338.98],
    "col_2": [
        15379.920000000002,
        1107140.42,
        8081.999999999999,
        1570.0300000000002,
        29468.539999999997,
    ],
}
float_double_df = pd.DataFrame.from_dict(float_double_data)


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


@pytest.mark.skipif(
    sys.version_info < (3, 8), reason="Feature not supported on Python 3.7 and earlier"
)
@pytest.mark.skipif(
    SA_VERSION < SA_2_0, reason="Feature not supported on SQLAlchemy 1.4 and earlier"
)
def test_float_double(cratedb_service):
    """
    Validate I/O with floating point numbers, specifically DOUBLE types.

    Motto: Do not lose precision when DOUBLE is required.
    """
    tablename = "pandas_double"
    engine = cratedb_service.database.engine
    float_double_df.to_sql(
        tablename,
        engine,
        if_exists="replace",
        index=False,
    )
    with engine.connect() as conn:
        conn.execute(sa.text(f"REFRESH TABLE {tablename}"))
    df_load = pd.read_sql_table(tablename, engine)

    before = float_double_df.sort_values(by="col_1", ignore_index=True)
    after = df_load.sort_values(by="col_1", ignore_index=True)

    pd.options.display.float_format = "{:.12f}".format
    assert_equal(before, after, check_exact=True)
