# -*- coding: utf-8; -*-
import warnings
from unittest import TestCase

from tests.util import ExtraAssertions


class SqlAlchemyWarningsTest(TestCase, ExtraAssertions):
    """
    Verify a few `DeprecationWarning` spots.

    https://docs.python.org/3/library/warnings.html#testing-warnings
    """

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
