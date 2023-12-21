.. _install:

=======
Install
=======

Learn how to install and get started with the Python client library for
`CrateDB`_.

.. rubric:: Table of contents

.. contents::
   :local:

Install
=======

.. highlight:: sh

The CrateDB Python client is available as package ``sqlalchemy-cratedb`` on `PyPI`_.

To install the most recent driver version, including the SQLAlchemy dialect
extension, run::

    pip install --upgrade sqlalchemy-cratedb

After that is done, you can import the library, like so:

.. code-block:: python

    >>> from sqlalchemy_cratedb import CrateDialect

Set up as a dependency
======================

There are `many ways`_ to add the ``sqlalchemy-cratedb`` package as a dependency to your
project. All of them work equally well. Please note that you may want to employ
package version pinning in order to keep the environment of your project stable
and reproducible, achieving `repeatable installations`_.


Next steps
==========

Learn how to :ref:`connect to CrateDB <connect>`.


.. _sqlalchemy-cratedb: https://pypi.org/project/sqlalchemy-cratedb/
.. _CrateDB: https://crate.io/products/cratedb/
.. _many ways: https://packaging.python.org/key_projects/
.. _PyPI: https://pypi.org/
.. _repeatable installations: https://pip.pypa.io/en/latest/topics/repeatable-installs/
