import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import registry as dialect_registry

from sqlalchemy_cratedb.sa_version import SA_2_0, SA_VERSION

if SA_VERSION < SA_2_0:
    raise pytest.skip("Only supported on SQLAlchemy 2.0 and higher", allow_module_level=True)

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# Registering the additional dialects manually seems to be needed when running
# under tests. Apparently, manual registration is not needed under regular
# circumstances, as this is wired through the `sqlalchemy.dialects` entrypoint
# registrations in `pyproject.toml`. It is definitively weird, but c'est la vie.
dialect_registry.register("crate.urllib3", "sqlalchemy_cratedb.dialect_more", "dialect_urllib3")
dialect_registry.register("crate.asyncpg", "sqlalchemy_cratedb.dialect_more", "dialect_asyncpg")
dialect_registry.register("crate.psycopg", "sqlalchemy_cratedb.dialect_more", "dialect_psycopg")


QUERY = sa.text("SELECT mountain, coordinates FROM sys.summits ORDER BY mountain LIMIT 3;")


def test_engine_sync_vanilla(cratedb_service):
    """
    crate:// -- Verify connectivity and data transport with vanilla HTTP-based driver.
    """
    port4200 = cratedb_service.cratedb.get_exposed_port(4200)
    engine = sa.create_engine(f"crate://crate@localhost:{port4200}/", echo=True)
    assert isinstance(engine, sa.engine.Engine)
    with engine.connect() as connection:
        result = connection.execute(QUERY)
        assert result.mappings().fetchone() == {
            "mountain": "Acherkogel",
            "coordinates": [10.95667, 47.18917],
        }


def test_engine_sync_urllib3(cratedb_service):
    """
    crate+urllib3:// -- Verify connectivity and data transport *explicitly* selecting the HTTP driver.
    """  # noqa: E501
    port4200 = cratedb_service.cratedb.get_exposed_port(4200)
    engine = sa.create_engine(
        f"crate+urllib3://crate@localhost:{port4200}/", isolation_level="AUTOCOMMIT", echo=True
    )
    assert isinstance(engine, sa.engine.Engine)
    with engine.connect() as connection:
        result = connection.execute(QUERY)
        assert result.mappings().fetchone() == {
            "mountain": "Acherkogel",
            "coordinates": [10.95667, 47.18917],
        }


def test_engine_sync_psycopg(cratedb_service):
    """
    crate+psycopg:// -- Verify connectivity and data transport using the psycopg driver (version 3).
    """
    port5432 = cratedb_service.cratedb.get_exposed_port(5432)
    engine = sa.create_engine(
        f"crate+psycopg://crate@localhost:{port5432}/", isolation_level="AUTOCOMMIT", echo=True
    )
    assert isinstance(engine, sa.engine.Engine)
    with engine.connect() as connection:
        result = connection.execute(QUERY)
        assert result.mappings().fetchone() == {
            "mountain": "Acherkogel",
            "coordinates": "(10.95667,47.18917)",
        }


@pytest.mark.asyncio
async def test_engine_async_psycopg(cratedb_service):
    """
    crate+psycopg:// -- Verify connectivity and data transport using the psycopg driver (version 3).
    This time, in asynchronous mode.
    """
    port5432 = cratedb_service.cratedb.get_exposed_port(5432)
    engine = create_async_engine(
        f"crate+psycopg://crate@localhost:{port5432}/", isolation_level="AUTOCOMMIT", echo=True
    )
    assert isinstance(engine, AsyncEngine)
    async with engine.begin() as conn:
        result = await conn.execute(QUERY)
        assert result.mappings().fetchone() == {
            "mountain": "Acherkogel",
            "coordinates": "(10.95667,47.18917)",
        }


@pytest.mark.asyncio
async def test_engine_async_asyncpg(cratedb_service):
    """
    crate+asyncpg:// -- Verify connectivity and data transport using the asyncpg driver.
    This exclusively uses asynchronous mode.
    """
    port5432 = cratedb_service.cratedb.get_exposed_port(5432)
    from asyncpg.pgproto.types import Point

    engine = create_async_engine(
        f"crate+asyncpg://crate@localhost:{port5432}/", isolation_level="AUTOCOMMIT", echo=True
    )
    assert isinstance(engine, AsyncEngine)
    async with engine.begin() as conn:
        result = await conn.execute(QUERY)
        assert result.mappings().fetchone() == {
            "mountain": "Acherkogel",
            "coordinates": Point(10.95667, 47.18917),
        }
