import unittest

import sqlalchemy as sa
from testcontainers.community.cratedb import CrateDBContainer


class ExtraAssertions:
    """
    Additional assert methods for unittest.

    - https://github.com/python/cpython/issues/71339
    - https://bugs.python.org/issue14819
    - https://bugs.python.org/file43047/extra_assertions.patch
    """

    def assertIsSubclass(self, cls, superclass, msg=None):
        try:
            r = issubclass(cls, superclass)
        except TypeError:
            if not isinstance(cls, type):
                self.fail(self._formatMessage(msg, "%r is not a class" % (cls,)))
            raise
        if not r:
            self.fail(self._formatMessage(msg, "%r is not a subclass of %r" % (cls, superclass)))


class ParametrizedTestCase(unittest.TestCase):
    """
    TestCase classes that want to be parametrized should
    inherit from this class.

    https://eli.thegreenplace.net/2011/08/02/python-unit-testing-parametrized-test-cases
    """

    def __init__(self, methodName="runTest", param=None):
        super(ParametrizedTestCase, self).__init__(methodName)
        self.param = param

    @staticmethod
    def parametrize(testcase_klass, param=None):
        """Create a suite containing all tests taken from the given
        subclass, passing them the parameter 'param'.
        """
        testloader = unittest.TestLoader()
        testnames = testloader.getTestCaseNames(testcase_klass)
        suite = unittest.TestSuite()
        for name in testnames:
            suite.addTest(testcase_klass(name, param=param))
        return suite


class CrateDBTestAdapter:
    """
    Run CrateDB in a container, with an engine and a few SQL shortcuts for the tests.
    """

    def __init__(self, crate_version: str):
        # Only `crate/crate` has nightly builds; its release tags are amd64-only, the official
        # `crate` image is not.
        image = "crate/crate:nightly" if crate_version == "nightly" else f"crate:{crate_version}"
        self.cratedb = CrateDBContainer(image=image)

    def start(self):
        self.cratedb.start()
        self.dburi = self.cratedb.get_connection_url()
        self.engine = sa.create_engine(self.dburi)

    def stop(self):
        self.engine.dispose()
        self.cratedb.stop()

    def run_sql(self, sql: str):
        with self.engine.begin() as connection:
            result = connection.execute(sa.text(sql))
            return result.fetchall() if result.returns_rows else None

    def refresh_table(self, name: str):
        self.run_sql(f"REFRESH TABLE {name}")

    def count_records(self, name: str) -> int:
        return self.run_sql(f"SELECT COUNT(*) FROM {name}")[0][0]
