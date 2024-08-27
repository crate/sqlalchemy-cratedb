import datetime as dt

import pytest
import sqlalchemy as sa
from sqlalchemy.event import listen
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from sqlalchemy_cratedb.sa_version import SA_1_4, SA_VERSION

try:
    from sqlalchemy.orm import declarative_base
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy_cratedb.support import (
    check_uniqueness_factory,
    patch_autoincrement_timestamp,
    refresh_after_dml,
)


@pytest.mark.skipif(
    SA_VERSION < SA_1_4, reason="Test case not supported on SQLAlchemy 1.3 and earlier"
)
def test_autoincrement_timestamp(cratedb_service):
    """
    Validate autoincrement columns using `sa.DateTime` columns.

    https://github.com/crate/sqlalchemy-cratedb/issues/77
    """
    patch_autoincrement_timestamp()

    engine = cratedb_service.database.engine
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


@pytest.mark.skipif(
    SA_VERSION < SA_1_4, reason="Feature not supported on SQLAlchemy 1.3 and earlier"
)
def test_check_uniqueness_factory(cratedb_service):
    """
    Validate basic synthetic UNIQUE constraints.

    https://github.com/crate/sqlalchemy-cratedb/issues/76
    """

    engine = cratedb_service.database.engine
    session = sessionmaker(bind=engine)()
    Base = declarative_base()

    # Define DDL.
    class FooBar(Base):
        __tablename__ = "foobar"
        id = sa.Column(sa.String, primary_key=True)
        name = sa.Column(sa.String)

    # Add synthetic UNIQUE constraint on `name` column.
    listen(FooBar, "before_insert", check_uniqueness_factory(FooBar, "name"))

    Base.metadata.drop_all(engine, checkfirst=True)
    Base.metadata.create_all(engine, checkfirst=True)

    # Insert baseline record.
    foo_item = FooBar(id="foo", name="foo")
    session.add(foo_item)
    session.commit()
    session.execute(sa.text("REFRESH TABLE foobar"))

    # Insert second record, violating the uniqueness constraint.
    bar_item = FooBar(id="bar", name="foo")
    session.add(bar_item)
    with pytest.raises(IntegrityError) as ex:
        session.commit()
    assert ex.match("DuplicateKeyException in table 'foobar' on constraint 'name'")


@pytest.mark.skipif(
    SA_VERSION < SA_1_4, reason="Feature not supported on SQLAlchemy 1.3 and earlier"
)
@pytest.mark.parametrize("mode", ["engine", "session"])
def test_refresh_after_dml(cratedb_service, mode):
    """
    Validate automatic `REFRESH TABLE` issuing works well.

    https://github.com/crate/sqlalchemy-cratedb/issues/83
    """
    engine = cratedb_service.database.engine
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
    assert (
        result is not None
    ), "Database result is empty. Most probably, `REFRESH TABLE` wasn't issued."

    # Compare outcome.
    assert result[0] == "foo"
