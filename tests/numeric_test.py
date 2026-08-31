from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

try:
    from sqlalchemy.orm import declarative_base
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy_cratedb.dialect import CrateDialect
from sqlalchemy_cratedb.sa_version import SA_1_4, SA_VERSION

# A value with more significant digits than a double can hold, so a column that
# is silently backed by an approximate type fails these tests instead of passing
# by accident.
EXACT_HIGH_PRECISION = Decimal("1.234567890123456789")

Base = declarative_base()


class Ledger(Base):
    __tablename__ = "ledger"
    name = sa.Column(sa.String, primary_key=True)
    amount = sa.Column(sa.Numeric(10, 2))
    amount_upper = sa.Column(sa.NUMERIC(10, 2))
    amount_decimal = sa.Column(sa.DECIMAL(10, 2))
    exact = sa.Column(sa.Numeric(38, 18))


@pytest.fixture
def session(cratedb_service):
    engine = cratedb_service.database.engine
    session = sessionmaker(bind=engine)()
    Base.metadata.drop_all(engine, checkfirst=True)
    Base.metadata.create_all(engine, checkfirst=True)
    return session


def render(type_):
    return CrateDialect().type_compiler.process(type_)


def render_cast(type_):
    statement = sa.select(sa.cast(sa.column("c"), type_))
    return str(statement.compile(dialect=CrateDialect())).split("AS ", 1)[1].rsplit(")", 2)[0]


@pytest.mark.parametrize(
    "type_",
    [
        sa.Numeric(10, 2),
        sa.NUMERIC(10, 2),
        sa.DECIMAL(10, 2),
    ],
    ids=["Numeric", "NUMERIC", "DECIMAL"],
)
def test_numeric_ddl_carries_precision_and_scale(type_):
    """
    `sa.DECIMAL` dispatches separately from the other two spellings; CrateDB
    treats the names as one type.
    """
    assert render(type_) == "NUMERIC(10, 2)"


def test_numeric_ddl_without_scale_carries_precision():
    assert render(sa.Numeric(10)) == "NUMERIC(10)"


@pytest.mark.skipif(SA_VERSION < SA_1_4, reason="Test case not supported on SQLAlchemy 1.3")
def test_numeric_cast_carries_precision_and_scale():
    column = sa.column("c")
    statement = sa.select(sa.cast(column, sa.Numeric(10, 2)))
    compiled = statement.compile(dialect=CrateDialect())
    assert "CAST(c AS NUMERIC(10, 2))" in str(compiled)


@pytest.mark.skipif(SA_VERSION < SA_1_4, reason="Test case not supported on SQLAlchemy 1.3")
def test_numeric_roundtrip_preserves_scale(session):
    """
    `Decimal` equality disregards the exponent, so the rendered form is what
    shows the scale survived.
    """
    session.add(
        Ledger(
            name="scale",
            amount=Decimal("1.25"),
            amount_upper=Decimal("2.50"),
            amount_decimal=Decimal("3.75"),
        )
    )
    session.commit()
    session.execute(sa.text("REFRESH TABLE ledger"))

    result = session.query(Ledger).filter(Ledger.name == "scale").one()
    assert str(result.amount) == "1.25"
    assert str(result.amount_upper) == "2.50"
    assert str(result.amount_decimal) == "3.75"


@pytest.mark.skipif(SA_VERSION < SA_1_4, reason="Test case not supported on SQLAlchemy 1.3")
def test_numeric_write_preserves_digits_beyond_double(session):
    session.add(Ledger(name="exact", exact=EXACT_HIGH_PRECISION))
    session.commit()
    session.execute(sa.text("REFRESH TABLE ledger"))

    stored = session.execute(
        sa.text("SELECT CAST(exact AS STRING) FROM ledger WHERE name = 'exact'")
    ).scalar()
    assert Decimal(stored) == EXACT_HIGH_PRECISION


def test_numeric_column_requires_precision():
    table = sa.Table("t", sa.MetaData(), sa.Column("c", sa.Numeric()))
    with pytest.raises(sa.exc.CompileError):
        sa.schema.CreateTable(table).compile(dialect=CrateDialect())


def test_numeric_cast_without_precision_is_unbounded():
    assert render_cast(sa.Numeric()) == "NUMERIC"


@pytest.mark.skipif(SA_VERSION < SA_1_4, reason="Test case not supported on SQLAlchemy 1.3")
def test_reflected_numeric_reads_as_decimal(session):
    """
    Reflection recovers the type from its name alone, so it carries no precision.
    """
    engine = session.bind
    session.add(Ledger(name="reflect", amount=Decimal("1.25")))
    session.commit()
    session.execute(sa.text("REFRESH TABLE ledger"))

    reflected = sa.Table("ledger", sa.MetaData(), autoload_with=engine)
    assert isinstance(reflected.columns["amount"].type, sa.Numeric)

    amount = session.execute(
        sa.select(reflected.c.amount).where(reflected.c.name == "reflect")
    ).scalar()
    assert amount == Decimal("1.25")
