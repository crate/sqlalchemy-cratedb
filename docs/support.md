(support-features)=
(support-utilities)=
# Support Features

The package bundles a few support and utility functions that try to fill a few
gaps you will observe when working with CrateDB, a distributed OLAP database,
since it lacks certain features, usually found in traditional OLTP databases.

A few of the features outlined below are referred to as [polyfills], and
emulate a few functionalities, for example, to satisfy compatibility issues on
downstream frameworks or test suites. You can use them at your disposal, but
you should know what you are doing, as some of them can seriously impact 
performance.

Other features include efficiency support utilities for 3rd-party frameworks,
which can be used to increase performance, mostly on INSERT operations.


(support-insert-bulk)=
## Bulk Support for pandas and Dask

:::{rubric} Background
:::
CrateDB's [](inv:crate-reference#http-bulk-ops) interface enables efficient
INSERT, UPDATE, and DELETE operations for batches of data. It enables
bulk operations, which are executed as single calls on the database server.

:::{rubric} Utility
:::
The `insert_bulk` utility provides efficient bulk data transfers when using
dataframe libraries like pandas and Dask. {ref}`dataframe` dedicates a whole
page to corresponding topics, about choosing the right chunk sizes, concurrency
settings, and beyond.

:::{rubric} Synopsis
:::
Use `method=insert_bulk` on pandas' or Dask's `to_sql()` method.
```python
import sqlalchemy as sa
from sqlalchemy_cratedb.support import insert_bulk
from pueblo.testing.pandas import makeTimeDataFrame

# Create a pandas DataFrame, and connect to CrateDB.
df = makeTimeDataFrame(nper=42, freq="S")
engine = sa.create_engine("crate://")

# Insert content of DataFrame using batches of records.
df.to_sql(
    name="testdrive",
    con=engine,
    if_exists="replace",
    index=False,
    method=insert_bulk,
)
```


(support-table-kwargs)=
## Context Manager `table_kwargs`

:::{rubric} Background
:::
CrateDB's special SQL DDL options to support [](inv:crate-reference#partitioned-tables),
[](inv:crate-reference#ddl-sharding), or [](inv:crate-reference#ddl-replication)
sometimes can't be configured easily when SQLAlchemy is wrapped into a 3rd-party
framework like pandas or Dask.

:::{rubric} Utility
:::
The `table_kwargs` utility is a context manager that is able to forward CrateDB's
dialect-specific table creation options to the `sa.Table()` constructor call sites
at runtime.

:::{rubric} Synopsis
:::
Using a context manager incantation like outlined below will render a
`PARTITIONED BY ("time")` SQL clause, without touching the call site of
`sa.Table(...)`.
```python
from sqlalchemy_cratedb.support import table_kwargs

with table_kwargs(crate_partitioned_by="time"):
    return df.to_sql(...)
```


(support-autoincrement)=
## Synthetic Autoincrement using Timestamps

:::{rubric} Background
:::
CrateDB does not provide traditional sequences or `SERIAL` data type support,
which enable automatically assigning incremental values when inserting records.


:::{rubric} Utility
:::
- The `patch_autoincrement_timestamp` utility emulates autoincrement /
  sequential ID behavior for designated columns, based on assigning timestamps
  on record insertion.
- It will simply assign `sa.func.now()` as a column `default` on the ORM model
  column. 
- It works on the SQLAlchemy column types `sa.BigInteger`, `sa.DateTime`,
  and `sa.String`.
- You can use it if adjusting ORM models for your database adapter is not
  an option.

:::{rubric} Synopsis
:::
After activating the patch, you can use `autoincrement=True` on column definitions.
```python
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base
from sqlalchemy_cratedb.support import patch_autoincrement_timestamp

# Enable patch.
patch_autoincrement_timestamp()

# Define database schema.
Base = declarative_base()

class FooBar(Base):
    id = sa.Column(sa.DateTime, primary_key=True, autoincrement=True)
```

:::{warning}
CrateDB's [`TIMESTAMP`](inv:crate-reference#type-timestamp) data type provides
milliseconds granularity. This has to be considered when evaluating collision
safety in high-traffic environments.
:::


(support-synthetic-refresh)=
## Synthetic Table REFRESH after DML

:::{rubric} Background
:::
CrateDB is [eventually consistent]. Data written with a former statement is
not guaranteed to be fetched with the next following select statement for the
affected rows.

Data written to CrateDB is flushed periodically, the refresh interval is
1000 milliseconds by default, and can be changed. More details can be found in
the reference documentation about [table refreshing](inv:crate-reference#refresh_data).

There are situations where stronger consistency is required, for example when
needing to satisfy test suites of 3rd party frameworks, which usually do not
take such special behavior of CrateDB into consideration.

:::{rubric} Utility
:::
- The `refresh_after_dml` utility will configure an SQLAlchemy engine or session
  to automatically invoke `REFRESH TABLE` statements after each DML
  operation (INSERT, UPDATE, DELETE).
- Only relevant (dirty) entities / tables will be considered to be refreshed.

:::{rubric} Synopsis
:::
```python
import sqlalchemy as sa
from sqlalchemy_cratedb.support import refresh_after_dml

engine = sa.create_engine("crate://")
refresh_after_dml(engine)
```

```python
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy_cratedb.support import refresh_after_dml

engine = sa.create_engine("crate://")
session = sessionmaker(bind=engine)()
refresh_after_dml(session)
```

:::{warning}
Refreshing the table after each DML operation can cause serious performance
degradations, and should only be used on low-volume, low-traffic data,
when applicable, and if you know what you are doing.
:::


(support-unique)=
## Synthetic UNIQUE Constraints

:::{rubric} Background
:::
CrateDB does not provide `UNIQUE` constraints in DDL statements. Because of its
distributed nature, supporting such a feature natively would cause expensive
database cluster operations, negating many benefits of using database clusters
firsthand.

:::{rubric} Utility
:::
- The `check_uniqueness_factory` utility emulates "unique constraints"
  functionality by querying the table for unique values before invoking
  SQL `INSERT` operations.
- It uses SQLALchemy [](inv:sa#orm_event_toplevel), more specifically
  the [before_insert] mapper event.
- When the uniqueness constraint is violated, the adapter will raise a
  corresponding exception.
  ```python
  IntegrityError: DuplicateKeyException in table 'foobar' on constraint 'name'
  ```

:::{rubric} Synopsis
:::
```python
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base
from sqlalchemy.event import listen
from sqlalchemy_cratedb.support import check_uniqueness_factory

# Define database schema.
Base = declarative_base()

class FooBar(Base):
    id = sa.Column(sa.String, primary_key=True)
    name = sa.Column(sa.String)

# Add synthetic UNIQUE constraint on `name` column.
listen(FooBar, "before_insert", check_uniqueness_factory(FooBar, "name"))
```

[before_insert]: https://docs.sqlalchemy.org/en/20/orm/events.html#sqlalchemy.orm.MapperEvents.before_insert

:::{note}
This feature will only work well if table data is consistent, which can be
ensured by invoking a `REFRESH TABLE` statement after any DML operation.
For conveniently enabling "always refresh", please refer to the documentation
section about [](#support-synthetic-refresh).
:::

:::{warning}
Querying the table before each INSERT operation can cause serious performance
degradations, and should only be used on low-volume, low-traffic data,
when applicable, and if you know what you are doing.
:::


[eventually consistent]: https://en.wikipedia.org/wiki/Eventual_consistency
[polyfills]: https://en.wikipedia.org/wiki/Polyfill_(programming)
