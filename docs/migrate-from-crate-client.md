(migrate-from-crate-python)=
# Migrate from `crate.client`

## Introduction
In June 2024, code from the package [crate\[sqlalchemy\]] has been transferred
to the package [sqlalchemy-cratedb]. For 80% of use cases, this will be
a drop-in replacement with no noticeable changes.

With the release of `crate-1.0.0` in November 2024, the SQLAlchemy dialect was
dropped from this package. See the "Upgrade procedure" section for further
information.

## Upgrade procedure
In order to continue using the CrateDB SQLAlchemy dialect, please install the
`sqlalchemy-cratedb` package [^1].
```shell
pip install --upgrade sqlalchemy-cratedb
```

## Code changes
If you are using CrateDB's special data types like `OBJECT`, `ARRAY`,
`GEO_POINT`, or `GEO_SHAPE`, and imported the relevant symbols from
`crate.client.sqlalchemy` before, you will need to adjust your imports
to use `sqlalchemy_cratedb` from now on, as outlined below.

### Previous imports
```python
from crate.client.sqlalchemy.dialect import CrateDialect
from crate.client.sqlalchemy.types import ObjectArray, ObjectType, FloatVector, Geopoint, Geoshape
from crate.client.sqlalchemy.predicates import match
from crate.client.sqlalchemy.compiler import CrateDDLCompiler, CrateTypeCompiler
```

### New imports
```python
from sqlalchemy_cratedb import dialect
from sqlalchemy_cratedb import ObjectArray, ObjectType, FloatVector, Geopoint, Geoshape
from sqlalchemy_cratedb import knn_match, match
from sqlalchemy_cratedb.compiler import CrateDDLCompiler, CrateTypeCompiler
```


[crate\[sqlalchemy\]]: https://pypi.org/project/crate/
[d2c42031f]: https://github.com/crate/cratedb-examples/commit/d2c42031f
[sqlalchemy-cratedb]: https://pypi.org/project/sqlalchemy-cratedb/

[^1]: When applicable, please also update your project dependencies to use
`sqlalchemy-cratedb` in your `pyproject.toml`, `requirements.txt`, or
`setup.py` files, **instead** of using the previous `crate[sqlalchemy]`
package. `sqlalchemy-cratedb` lists `crate` as a dependency and will
automatically pull in the right version. A typical dependency update will
look like [d2c42031f].
