import datetime as dt
import sys

import pytest
import sqlalchemy as sa
from sqlalchemy.event import listen
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base, sessionmaker

from sqlalchemy_cratedb.sa_version import SA_2_0, SA_VERSION
from sqlalchemy_cratedb.support import (
    check_uniqueness_factory,
    patch_autoincrement_timestamp,
    refresh_after_dml,
    refresh_dirty,
)

requires_asyncio_types = pytest.mark.skipif(
    SA_VERSION < SA_2_0, reason="`async_sessionmaker` is new in SQLAlchemy 2.0"
)


def test_autoincrement_timestamp(cratedb_service):
    """
    Validate autoincrement columns using `sa.DateTime` columns.

    https://github.com/crate/sqlalchemy-cratedb/issues/77
    """
    patch_autoincrement_timestamp()

    engine = cratedb_service.engine
    session = sessionmaker(bind=engine)()
    Base = declarative_base()

    # Define DDL.
    class FooBar(Base):
        __tablename__ = "foobar"
        id = sa.Column(sa.String, primary_key=True)
        date = sa.Column(sa.DateTime, autoincrement=True)
        number = sa.Column(sa.BigInteger, autoincrement=True)
        string = sa.Column(sa.String, autoincrement=True)

    Base.metadata.drop_all(engine, checkfirst=True)
    Base.metadata.create_all(engine, checkfirst=True)

    # Insert record.
    foo_item = FooBar(id="foo")
    session.add(foo_item)
    session.commit()
    session.execute(sa.text("REFRESH TABLE foobar"))

    # Query record.
    result = (
        session.execute(sa.select(FooBar.date, FooBar.number, FooBar.string)).mappings().first()
    )

    # Compare outcome.
    assert result["date"].year == dt.datetime.now().year
    assert result["number"] >= 1718846016235
    assert result["string"] >= "1718846016235"


def test_check_uniqueness_factory(cratedb_service):
    """
    Validate basic synthetic UNIQUE constraints.

    https://github.com/crate/sqlalchemy-cratedb/issues/76
    """

    engine = cratedb_service.engine
    session = sessionmaker(bind=engine)()
    Base = declarative_base()

    # Define DDL.
    class FooBar(Base):
        __tablename__ = "foobar"
        id = sa.Column(sa.String, primary_key=True)
        name = sa.Column(sa.String)

    # Add synthetic UNIQUE constraint on `name` column.
    listen(FooBar, "before_insert", check_uniqueness_factory(FooBar, "id", "name"))

    Base.metadata.drop_all(engine, checkfirst=True)
    Base.metadata.create_all(engine, checkfirst=True)

    # Insert baseline record.
    foo_item = FooBar(id="foo", name="foo")
    session.add(foo_item)
    session.commit()
    session.execute(sa.text("REFRESH TABLE foobar"))

    # Insert second record, violating the uniqueness constraint.
    bar_item = FooBar(id="foo", name="foo")
    session.add(bar_item)
    with pytest.raises(IntegrityError) as ex:
        session.commit()
    assert ex.match("DuplicateKeyException in table 'foobar' on constraint 'id-name'")


@pytest.mark.parametrize("mode", ["engine", "session"])
def test_refresh_after_dml(cratedb_service, mode):
    """
    Validate automatic `REFRESH TABLE` issuing works well.

    https://github.com/crate/sqlalchemy-cratedb/issues/83
    """
    engine = cratedb_service.engine
    session = sessionmaker(bind=engine)()
    Base = declarative_base()

    # Enable automatic refresh.
    if mode == "engine":
        refresh_after_dml(engine)
    elif mode == "session":
        refresh_after_dml(session)
    else:
        raise ValueError(f"Unable to enable automatic refresh with mode: {mode}")

    # Define DDL.
    class FooBar(Base):
        __tablename__ = "foobar"
        id = sa.Column(sa.String, primary_key=True)

    Base.metadata.drop_all(engine, checkfirst=True)
    Base.metadata.create_all(engine, checkfirst=True)

    # Insert baseline record.
    foo_item = FooBar(id="foo")
    session.add(foo_item)
    session.commit()

    # Query record.
    query = session.query(FooBar.id)
    result = query.first()

    # Sanity checks.
    assert result is not None, (
        "Database result is empty. Most probably, `REFRESH TABLE` wasn't issued."
    )

    # Compare outcome.
    assert result[0] == "foo"


@pytest.fixture
def async_engine():
    """
    An `AsyncEngine` that does no IO. Attaching listeners needs no async driver.
    """
    from sqlalchemy.ext.asyncio import AsyncEngine

    engine = sa.create_engine("crate://")
    engine.dialect.is_async = True
    return AsyncEngine(engine)


def refreshes(session: sa.orm.Session) -> bool:
    return refresh_dirty in list(session.dispatch.after_flush)


@requires_asyncio_types
def test_refresh_after_dml_async_engine(async_engine):
    refresh_after_dml(async_engine)
    assert len(async_engine.sync_engine.dispatch.after_execute) == 1


@requires_asyncio_types
def test_refresh_after_dml_async_session(async_engine):
    from sqlalchemy.ext.asyncio import AsyncSession

    session = AsyncSession(async_engine)
    refresh_after_dml(session)
    assert refreshes(session.sync_session)
    assert not refreshes(AsyncSession(async_engine).sync_session)


@requires_asyncio_types
def test_refresh_after_dml_async_sessionmaker(async_engine):
    """
    Only the sessions of the given factory refresh, not every `Session` in the process.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(async_engine)
    refresh_after_dml(factory)
    assert refreshes(factory().sync_session)
    assert not refreshes(sa.orm.Session())
    assert not refreshes(AsyncSession(async_engine).sync_session)
    assert not refreshes(async_sessionmaker(async_engine)().sync_session)


@requires_asyncio_types
def test_refresh_after_dml_async_sessionmaker_keeps_sync_session_class(async_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    class TenantSession(sa.orm.Session):
        pass

    factory = async_sessionmaker(async_engine, sync_session_class=TenantSession)
    refresh_after_dml(factory)
    session = factory().sync_session
    assert isinstance(session, TenantSession)
    assert refreshes(session)
    assert not refreshes(TenantSession())


@requires_asyncio_types
def test_refresh_after_dml_async_sessionmaker_twice(async_engine):
    """
    Calling it again on the same factory does not refresh twice per flush.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(async_engine)
    refresh_after_dml(factory)
    refresh_after_dml(factory)
    assert list(factory().sync_session.dispatch.after_flush).count(refresh_dirty) == 1


def test_refresh_after_dml_unknown_type():
    with pytest.raises(TypeError, match="Unknown type"):
        refresh_after_dml(sa.MetaData())


def test_refresh_after_dml_unknown_type_without_asyncio(monkeypatch):
    """
    Without `greenlet`, importing `sqlalchemy.ext.asyncio` fails on SQLAlchemy 2.1.
    """
    monkeypatch.setitem(sys.modules, "sqlalchemy.ext.asyncio", None)
    with pytest.raises(TypeError, match="Unknown type"):
        refresh_after_dml(sa.MetaData())
