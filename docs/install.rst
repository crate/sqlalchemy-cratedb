.. _install:

=======
Install
=======

Learn how to install and get started with the SQLAlchemy dialect for
`CrateDB`_. The package is available from `PyPI`_ at `sqlalchemy-cratedb`_.

.. rubric:: Table of contents

.. contents::
   :local:

Install
=======

To install the most recent driver version, including the SQLAlchemy dialect
extension, run:

.. code-block:: shell

    pip install --upgrade sqlalchemy-cratedb

After that is done, you can import the library, like so:

.. code-block:: python

    >>> from sqlalchemy_cratedb import dialect

Set up as a dependency
======================

There are `many ways`_ to add the ``sqlalchemy-cratedb`` package as a dependency to your
project. All of them work equally well. Please note that you may want to employ
package version pinning in order to keep the environment of your project stable
and reproducible, achieving `repeatable installations`_.


Next steps
==========

Learn how to :ref:`get started <getting-started>`, or how to :ref:`connect to CrateDB <connect>`.


.. _CrateDB: https://cratedb.com/database
.. _many ways: https://packaging.python.org/key_projects/
.. _PyPI: https://pypi.org/
.. _repeatable installations: https://pip.pypa.io/en/latest/topics/repeatable-installs/
.. _sqlalchemy-cratedb: https://pypi.org/project/sqlalchemy-cratedb/
