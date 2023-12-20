# Backlog

## Iteration +1
From dialect split-off.
- Re-enable parameterized test cases.
  ```
  tests.addTest(ParametrizedTestCase.parametrize(SqlAlchemyCompilerTest, param={"server_version_info": None}))
  tests.addTest(ParametrizedTestCase.parametrize(SqlAlchemyCompilerTest, param={"server_version_info": (4, 0, 12)}))
  tests.addTest(ParametrizedTestCase.parametrize(SqlAlchemyCompilerTest, param={"server_version_info": (4, 1, 10)}))
  ```
- Re-enable doctests.

