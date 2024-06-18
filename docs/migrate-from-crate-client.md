(migrate-from-crate-python)=
# Migrate from `crate.client`

In June 2024, code from the package [crate\[sqlalchemy\]] has been transferred
to the package [sqlalchemy-cratedb]. For 80% of use cases, this will be
a drop-in replacement with no noticeable changes.

However, if you use CrateDB's special data types like `OBJECT`, `ARRAY`,
`GEO_POINT`, or `GEO_SHAPE`, and imported the relevant symbols from
`crate.client.sqlalchemy`, you will need to import the same symbols from
`sqlalchemy_cratedb` from now on.

## Upgrade procedure

- Swap dependency definition from `crate[sqlalchemy]` to `sqlalchemy-cratedb`
  in your `pyproject.toml`, `requirements.txt`, or `setup.py`.
- Adjust symbol imports as outlined below.

### Symbol import adjustments
```python
# Previous import
# from crate.client.sqlalchemy.dialect import CrateDialect

# New import
from sqlalchemy_cratedb import dialect
```

```python
# Previous import
# from crate.client.sqlalchemy.types import ObjectArray, ObjectType, FloatVector, Geopoint, Geoshape

# New import
from sqlalchemy_cratedb import ObjectArray, ObjectType, FloatVector, Geopoint, Geoshape
```

```python
# Previous import
from crate.client.sqlalchemy.compiler import CrateDDLCompiler, CrateTypeCompiler

# New import
from sqlalchemy_cratedb.compiler import CrateDDLCompiler, CrateTypeCompiler
```

```python
# Previous import
# from crate.client.sqlalchemy.predicates import match

# New import
from sqlalchemy_cratedb import knn_match, match
```


[crate\[sqlalchemy\]]: https://pypi.org/project/crate/
[sqlalchemy-cratedb]: https://pypi.org/project/sqlalchemy-cratedb/
