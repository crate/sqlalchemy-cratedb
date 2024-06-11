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

## Iteration +2
- https://docs.sqlalchemy.org/en/20/faq/performance.html
- Is ``RETURNING`` properly supported?
  https://docs.sqlalchemy.org/en/20/changelog/whatsnew_20.html#optimized-orm-bulk-insert-now-implemented-for-all-backends-other-than-mysql
- Bulk *UPDATES*
- https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html#orm-queryguide-upsert
  via: https://github.com/sqlalchemy/sqlalchemy/discussions/6935#discussioncomment-1233465
- Result streaming via server-side cursor
  - https://docs.sqlalchemy.org/en/20/core/connections.html#sqlalchemy.engine.Connection.execution_options.params.stream_results
  - https://docs.sqlalchemy.org/en/20/core/connections.html#sqlalchemy.engine.Result.yield_per
- https://github.com/jamescasbon/vertica-sqlalchemy
