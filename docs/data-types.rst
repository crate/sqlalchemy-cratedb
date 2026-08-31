.. _data-types:

==========
Data types
==========

.. NOTE::

    The type that ``date`` and ``datetime`` objects are mapped to, depends on the
    CrateDB column type.

.. NOTE::

    When using ``date`` or ``datetime`` objects with ``timezone`` information,
    the value is implicitly converted to a `Unix time`_ (epoch) timestamp, i.e.
    the number of seconds which have passed since 00:00:00 UTC on
    Thursday, 1 January 1970.

    This means, when inserting or updating records using timezone-aware Python
    ``date`` or ``datetime`` objects, timezone information will not be
    preserved. If you need to store it, you will need to use a separate column.

.. NOTE::

    Inserting timezone-aware ``datetime`` objects is supported; the value is
    converted to a UTC instant on the way in, as outlined above. On the way
    out, the dialect returns **naive** ``datetime`` objects in UTC by default.

    To read values back as timezone-aware ``datetime`` objects instead,
    configure the CrateDB driver's ``time_zone`` argument, for example::

        from sqlalchemy import create_engine

        engine = create_engine(
            "crate://localhost:4200",
            connect_args={"time_zone": "+0530"},
        )

    The driver then converts ``TIMESTAMP`` columns to timezone-aware
    ``datetime`` objects transparently. See `TIMESTAMP conversion with time
    zone`_ in the driver documentation for the accepted ``time_zone`` values.


.. _data-types-sqlalchemy:

SQLAlchemy
==========

This section documents data types for the CrateDB :ref:`SQLAlchemy dialect
<using-sqlalchemy>`.

.. _sqlalchemy-type-map:

Type map
--------

The CrateDB dialect maps between data types like so:

================= =========================================
CrateDB           SQLAlchemy
================= =========================================
`boolean`__       `Boolean`__
`byte`__          `SmallInteger`__
`short`__         `SmallInteger`__
`integer`__       `Integer`__
`long`__          `BigInteger`__
`numeric`__       `Numeric`__
`float`__         `Float`__
`float_vector`__  ``FloatVector``
`double`__        `Double`__
`timestamp`__     `TIMESTAMP`__
`string`__        `String`__
`array`__         `ARRAY`__
`object`__        :ref:`object` |nbsp| (extension type)
`object`__        ``JSON``
`object`__        ``JSONB``
`array(object)`__ :ref:`objectarray` |nbsp| (extension type)
`geo_point`__     :ref:`geopoint` |nbsp| (extension type)
`geo_shape`__     :ref:`geoshape` |nbsp| (extension type)
================= =========================================


__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#boolean
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.Boolean
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#numeric-data
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.SmallInteger
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#numeric-data
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.SmallInteger
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#numeric-data
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.Integer
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#numeric-data
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.BigInteger
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#numeric-precision-scale
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.Numeric
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#numeric-data
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.Float
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#float-vector
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#numeric-data
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.Double
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#dates-and-times
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.TIMESTAMP
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#character-data
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.String
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#array
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.ARRAY
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#object
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#object
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#object
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#array
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#geo-point
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#geo-shape


.. note::

    ``NUMERIC`` and ``DECIMAL`` name the same type, rendered into the DDL as
    ``NUMERIC(precision, scale)``. CrateDB stores up to 38 digits, and requires
    the precision, so declaring a column without one raises a compile error
    rather than emitting DDL the server would reject. Giving a precision but no
    scale means a scale of zero, as it does in standard SQL, so
    ``Numeric(10)`` holds whole numbers. Storing the type requires CrateDB 5.9
    or later.

    Values are written exactly: a ``Decimal`` reaches the database with every
    digit it was given. Reading is narrower, because the driver reads the
    numbers in a response as floats, so a returned value carries at most the
    digits a float holds.

    Reflection recovers a column's type from its name alone, so a reflected
    ``NUMERIC`` column carries no precision and cannot be rendered back into
    DDL.


.. _TIMESTAMP conversion with time zone: https://cratedb.com/docs/python/en/latest/query.html#timestamp-conversion-with-time-zone
.. _Unix time: https://en.wikipedia.org/wiki/Unix_time
