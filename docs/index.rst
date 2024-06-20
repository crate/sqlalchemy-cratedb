.. _index:

##############################
SQLAlchemy dialect for CrateDB
##############################

.. rubric:: Table of contents

.. contents::
    :local:
    :depth: 1


*****
About
*****

The :ref:`CrateDB dialect <using-sqlalchemy>` for `SQLAlchemy`_ provides adapters
for `CrateDB`_ and SQLAlchemy. The supported versions are 1.3, 1.4, and 2.0.
The package is available from `PyPI`_ at `sqlalchemy-cratedb`_.

The connector can be used to connect to both `CrateDB`_ and `CrateDB
Cloud`_, and is verified to work on Linux, macOS, and Windows. It is used by
pandas, Dask, and many other libraries and applications connecting to
CrateDB from the Python ecosystem. It is verified to work with CPython, but
it has also been tested successfully with `PyPy`_.

.. note::

    If you are upgrading from ``crate[sqlalchemy]`` to ``sqlalchemy-cratedb``,
    please read this section carefully.

    .. toctree::
        :titlesonly:

        migrate-from-crate-client



************
Introduction
************

Please consult the `SQLAlchemy tutorial`_, and the general `SQLAlchemy
documentation`_.
For more detailed information about how to install the dialect package, how to
connect to a CrateDB cluster, and how to run queries, consult the resources
referenced below.


************
Installation
************

Install package from PyPI.

.. code-block:: shell

    pip install --upgrade sqlalchemy-cratedb

More installation details can be found over here.

.. toctree::
    :titlesonly:

    install


.. _features:

********
Features
********

The CrateDB dialect for `SQLAlchemy`_ offers convenient ORM access and supports
CrateDB's container data types ``OBJECT`` and ``ARRAY``, its vector data type
``FLOAT_VECTOR``, and geospatial data types using `GeoJSON`_, supporting different
kinds of `GeoJSON geometry objects`_.

.. toctree::
    :maxdepth: 2

    overview


.. _synopsis:

Synopsis
========

Connect to CrateDB instance running on ``localhost``.

.. code-block:: python

    # Connect using SQLAlchemy Core.
    import sqlalchemy as sa
    from pprint import pp

    dburi = "crate://localhost:4200"
    query = "SELECT country, mountain, coordinates, height FROM sys.summits ORDER BY country;"
    
    engine = sa.create_engine(dburi, echo=True)
    with engine.connect() as connection:
        with connection.execute(sa.text(query)) as result:
            pp(result.mappings().fetchall())

Connect to `CrateDB Cloud`_.

.. code-block:: python

    # Connect using SQLAlchemy Core.
    import sqlalchemy as sa
    dburi = "crate://admin:<PASSWORD>@example.aks1.westeurope.azure.cratedb.net:4200?ssl=true"
    engine = sa.create_engine(dburi, echo=True)

Load results into `pandas`_ DataFrame.

.. code-block:: shell

    pip install pandas

.. code-block:: python

    # Connect using SQLAlchemy Core and pandas.
    import pandas as pd
    import sqlalchemy as sa
    
    dburi = "crate://localhost:4200"
    query = "SELECT * FROM sys.summits ORDER BY country;"
    
    engine = sa.create_engine(dburi, echo=True)
    with engine.connect() as connection:
        df = pd.read_sql(sql=sa.text(query), con=connection)
        df.info()
        print(df)


Data Types
==========

The :ref:`DB API driver <crate-python:index>` and the SQLAlchemy dialect
support :ref:`CrateDB's data types <crate-reference:data-types>` to different
degrees.
For more information, please consult the :ref:`data-types` and :ref:`SQLAlchemy
extension types <using-extension-types>` documentation pages.

.. toctree::
    :maxdepth: 2
    :hidden:

    data-types

Support Utilities
=================

The package bundles a few support and utility functions that try to fill a few
gaps you will observe when working with CrateDB, when compared with other
databases.
Due to its distributed nature, CrateDB's behavior and features differ from those
found in other RDBMS systems.

.. toctree::
    :maxdepth: 2

    support


.. _examples:
.. _by-example:
.. _sqlalchemy-by-example:

********
Examples
********

This section enumerates concise examples demonstrating the
use of the SQLAlchemy dialect.

.. toctree::
    :maxdepth: 1

    getting-started
    crud
    working-with-types
    advanced-querying
    inspection-reflection
    dataframe

.. rubric:: See also

- Executable code examples are maintained within the `cratedb-examples repository`_.
- `Using CrateDB with pandas, Dask, and Polars`_ has corresponding code snippets
  about how to connect to CrateDB using popular data frame libraries, and how to
  load and export data.
- The `Apache Superset`_ and `FIWARE QuantumLeap data historian`_ projects.



*******************
Project information
*******************

Resources
=========
- `Source code <https://github.com/crate/sqlalchemy-cratedb>`_
- `Documentation <https://github.com/crate/sqlalchemy-cratedb>`_
- `Python Package Index (PyPI) <https://pypi.org/project/sqlalchemy-cratedb/>`_

Contributions
=============
The SQLAlchemy dialect for CrateDB is an open source project, and is `managed on
GitHub`_.
Every kind of contribution, feedback, or patch, is much welcome. `Create an
issue`_ or submit a patch if you think we should include a new feature, or to
report or fix a bug.

Development
===========
In order to setup a development environment on your workstation, please head
over to the `development sandbox`_ documentation. When you see the software
tests succeed, you should be ready to start hacking.

Page index
==========
The full index for all documentation pages can be inspected at :ref:`index-all`.

License
=======
The project is licensed under the terms of the Apache 2.0 license, like
`CrateDB itself <CrateDB source_>`_, see `LICENSE`_.


.. _Apache Superset: https://github.com/apache/superset
.. _CrateDB: https://cratedb.com/database
.. _CrateDB Cloud: https://console.cratedb.cloud/
.. _CrateDB source: https://github.com/crate/crate
.. _Create an issue: https://github.com/crate/sqlalchemy-cratedb/issues
.. _development sandbox: https://github.com/crate/sqlalchemy-cratedb/blob/main/DEVELOP.md
.. _cratedb-examples repository: https://github.com/crate/cratedb-examples/tree/main/by-language
.. _FIWARE QuantumLeap data historian: https://github.com/orchestracities/ngsi-timeseries-api
.. _GeoJSON: https://geojson.org/
.. _GeoJSON geometry objects: https://tools.ietf.org/html/rfc7946#section-3.1
.. _LICENSE: https://github.com/crate/sqlalchemy-cratedb/blob/main/LICENSE
.. _managed on GitHub: https://github.com/crate/sqlalchemy-cratedb
.. _pandas: https://pandas.pydata.org/
.. _PEP 249: https://peps.python.org/pep-0249/
.. _PyPI: https://pypi.org/
.. _PyPy: https://www.pypy.org/
.. _SQLAlchemy: https://www.sqlalchemy.org/
.. _SQLAlchemy documentation: https://docs.sqlalchemy.org/
.. _SQLAlchemy tutorial: https://docs.sqlalchemy.org/en/latest/tutorial/
.. _sqlalchemy-cratedb: https://pypi.org/project/sqlalchemy-cratedb/
.. _Using CrateDB with pandas, Dask, and Polars: https://github.com/crate/cratedb-examples/tree/main/by-dataframe
