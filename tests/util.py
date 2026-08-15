import unittest


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
