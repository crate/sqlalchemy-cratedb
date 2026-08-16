"""
## About
SQLAlchemy data type implementation for CrateDB's `FLOAT_VECTOR` type.

## References
- https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#float-vector
- https://cratedb.com/docs/crate/reference/en/latest/general/builtins/scalar-functions.html#scalar-knn-match

## Details
The implementation is based on SQLAlchemy's `TypeDecorator`, and also
offers compiler support.

## Notes
CrateDB currently only supports the similarity function `VectorSimilarityFunction.EUCLIDEAN`.
-- https://github.com/crate/crate/blob/5.5.1/server/src/main/java/io/crate/types/FloatVectorType.java#L55

pgvector use a comparator to apply different similarity functions as operators,
see `pgvector.sqlalchemy.Vector.comparator_factory`.

<->: l2/euclidean_distance
<#>: max_inner_product
<=>: cosine_distance

## Backlog
- After dropping support for SQLAlchemy 1.3, use
  `class FloatVector(sa.TypeDecorator[t.Sequence[float]]):`

## Origin
This module is based on the corresponding pgvector implementation
by Andrew Kane. Thank you.

The MIT License (MIT)
Copyright (c) 2021-2023 Andrew Kane
https://github.com/pgvector/pgvector-python
"""

import typing as t

if t.TYPE_CHECKING:
    import numpy.typing as npt  # pragma: no cover

import sqlalchemy as sa
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ColumnElement, literal

__all__ = [
    "from_db",
    "knn_match",
    "to_db",
    "FloatVector",
]


def from_db(value: t.Iterable) -> t.Optional["npt.ArrayLike"]:
    import numpy as np

    # from `pgvector.utils`
    # could be ndarray if already cast by lower-level driver
    if value is None or isinstance(value, np.ndarray):
        return value

    return np.array(value, dtype=np.float32)


def to_db(value: t.Any, dim: t.Optional[int] = None) -> t.Optional[t.List]:
    import numpy as np

    # from `pgvector.utils`
    if value is None:
        return value

    if isinstance(value, np.ndarray):
        if value.ndim != 1:
            raise ValueError("expected ndim to be 1")

        if not np.issubdtype(value.dtype, np.integer) and not np.issubdtype(
            value.dtype, np.floating
        ):
            raise ValueError("dtype must be numeric")

        value = value.tolist()

    if dim is not None and len(value) != dim:
        raise ValueError("expected %d dimensions, not %d" % (dim, len(value)))

    return value


class FloatVector(sa.TypeDecorator):
    """
    SQLAlchemy `FloatVector` data type for CrateDB.
    """

    cache_ok = False

    __visit_name__ = "FLOAT_VECTOR"

    _is_array = True

    zero_indexes = False

    impl = sa.ARRAY

    def __init__(self, dimensions: int = None):
        super().__init__(sa.FLOAT, dimensions=dimensions)

    def as_generic(self, allow_nulltype=False):
        return sa.ARRAY(item_type=sa.FLOAT)

    @property
    def python_type(self):
        return list

    def bind_processor(self, dialect: sa.engine.Dialect) -> t.Callable:
        def process(value: t.Iterable) -> t.Optional[t.List]:
            return to_db(value, self.dimensions)

        return process

    def result_processor(self, dialect: sa.engine.Dialect, coltype: t.Any) -> t.Callable:
        def process(value: t.Any) -> t.Optional["npt.ArrayLike"]:
            return from_db(value)

        return process


class KnnMatch(ColumnElement):
    """
    Wrap CrateDB's `KNN_MATCH` function into an SQLAlchemy function.

    https://cratedb.com/docs/crate/reference/en/latest/general/builtins/scalar-functions.html#scalar-knn-match
    """

    inherit_cache = True

    def __init__(self, column, term, k=None):
        super().__init__()
        self.column = column
        self.term = term
        self.k = k

    def compile_column(self, compiler):
        return compiler.process(self.column)

    def compile_term(self, compiler):
        return compiler.process(literal(self.term))

    def compile_k(self, compiler):
        return compiler.process(literal(self.k))


def knn_match(column, term, k):
    """
    Generate a match predicate for vector search.

    :param column: A reference to a column or an index.

    :param term: The term to match against. This is an array of floating point
     values, which is compared to other vectors using a HNSW index search.

    :param k: The `k` argument determines the number of nearest neighbours to
    search in the index.
    """
    return KnnMatch(column, term, k)


@compiles(KnnMatch)
def compile_knn_match(knn_match, compiler, **kwargs):
    """
    Clause compiler for `KNN_MATCH`.
    """
    return "KNN_MATCH(%s, %s, %s)" % (
        knn_match.compile_column(compiler),
        knn_match.compile_term(compiler),
        knn_match.compile_k(compiler),
    )
