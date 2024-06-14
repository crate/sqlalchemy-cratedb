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
`long`__          `NUMERIC`__
`float`__         `Float`__
`float_vector`__  ``FloatVector``
`double`__        `DECIMAL`__
`timestamp`__     `TIMESTAMP`__
`string`__        `String`__
`array`__         `ARRAY`__
`object`__        :ref:`object` |nbsp| (extension type)
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
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.NUMERIC
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#numeric-data
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.Float
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#float-vector
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#numeric-data
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.DECIMAL
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#dates-and-times
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.TIMESTAMP
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#character-data
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.String
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#array
__ http://docs.sqlalchemy.org/en/latest/core/type_basics.html#sqlalchemy.types.ARRAY
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#object
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#array
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#geo-point
__ https://cratedb.com/docs/crate/reference/en/latest/general/ddl/data-types.html#geo-shape


.. _Unix time: https://en.wikipedia.org/wiki/Unix_time
