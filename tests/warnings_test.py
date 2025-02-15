# -*- coding: utf-8; -*-
import sys
import warnings
from unittest import TestCase, skipIf

from sqlalchemy_cratedb.sa_version import SA_1_4, SA_VERSION
from tests.util import ExtraAssertions


class SqlAlchemyWarningsTest(TestCase, ExtraAssertions):
    """
    Verify a few `DeprecationWarning` spots.

    https://docs.python.org/3/library/warnings.html#testing-warnings
    """

    @skipIf(
        SA_VERSION >= SA_1_4,
        "There is no deprecation warning for SQLAlchemy 1.3 on higher versions",
    )
    def test_sa13_deprecation_warning(self):
        """
        Verify that a `DeprecationWarning` is issued when running SQLAlchemy 1.3.
        """
        with warnings.catch_warnings(record=True) as w:
            # Cause all warnings to always be triggered.
            warnings.simplefilter("always")

            # Trigger a warning by importing the SQLAlchemy dialect module.
            # Because it already has been loaded, unload it beforehand.
            del sys.modules["sqlalchemy_cratedb"]
            import sqlalchemy_cratedb  # noqa: F401

            # Verify details of the SA13 EOL/deprecation warning.
            self.assertEqual(len(w), 1)
            self.assertIsSubclass(w[-1].category, DeprecationWarning)
            self.assertIn("SQLAlchemy 1.3 is effectively EOL.", str(w[-1].message))

    def test_craty_object_deprecation_warning(self):
        """
        Verify that a `DeprecationWarning` is issued when accessing the deprecated
        module variables `Craty`, and `Object`. The new type is called `ObjectType`.
        """

        with warnings.catch_warnings(record=True) as w:
            # Import the deprecated symbol.
            from sqlalchemy_cratedb.type.object import Craty  # noqa: F401

            # Verify details of the deprecation warning.
            self.assertEqual(len(w), 1)
            self.assertIsSubclass(w[-1].category, DeprecationWarning)
            self.assertIn(
                "Craty is deprecated and will be removed in future releases. "
                "Please use ObjectType instead.",
                str(w[-1].message),
            )

        with warnings.catch_warnings(record=True) as w:
            # Import the deprecated symbol.
            from sqlalchemy_cratedb.type.object import Object  # noqa: F401

            # Verify details of the deprecation warning.
            self.assertEqual(len(w), 1)
            self.assertIsSubclass(w[-1].category, DeprecationWarning)
            self.assertIn(
                "Object is deprecated and will be removed in future releases. "
                "Please use ObjectType instead.",
                str(w[-1].message),
            )
