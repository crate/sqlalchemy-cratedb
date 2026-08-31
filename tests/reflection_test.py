import logging

import pytest
import sqlalchemy as sa
from sqlalchemy import types as sqltypes

from sqlalchemy_cratedb import Geopoint, Geoshape, ObjectArray
from sqlalchemy_cratedb.dialect import ARRAY_SUFFIX, TYPES_MAP, CrateDialect
from sqlalchemy_cratedb.sa_version import SA_1_4, SA_2_0, SA_VERSION

# CrateDB reports `regproc` for the `pg_catalog` columns holding a reference to
# a function. No table can declare one, so it has no DDL spelling to map to.
UNRESOLVABLE = "regproc"


def reflected_column(data_type):
    return sa.Column("c", CrateDialect()._resolve_type(data_type))


def render_type(data_type):
    """
    The map holds classes as well as instances; `to_instance` matches what a
    `Column` does with either.
    """
    dialect = CrateDialect()
    return dialect.type_compiler.process(sqltypes.to_instance(dialect._resolve_type(data_type)))


def render_ddl(data_type):
    dialect = CrateDialect()
    table = sa.Table("t", sa.MetaData(), reflected_column(data_type))
    return str(sa.schema.CreateTable(table).compile(dialect=dialect))


@pytest.mark.parametrize(
    ("data_type", "rendered"),
    [
        ("geo_point", "GEO_POINT"),
        ("geo_shape", "GEO_SHAPE"),
    ],
)
def test_reflected_geo_column_renders_its_ddl(data_type, rendered):
    assert "c {0}".format(rendered) in render_ddl(data_type)


def test_reflected_geo_column_resolves_to_the_geo_type():
    """
    The types the package already offers, rather than a substitute that merely
    renders the same DDL.
    """
    dialect = CrateDialect()
    assert dialect._resolve_type("geo_point") is Geopoint
    assert dialect._resolve_type("geo_shape") is Geoshape


@pytest.mark.parametrize(
    ("data_type", "rendered"),
    [
        ("boolean_array", "ARRAY(BOOLEAN)"),
        ("short_array", "ARRAY(SHORT)"),
        ("smallint_array", "ARRAY(SHORT)"),
        ("integer_array", "ARRAY(INT)"),
        ("long_array", "ARRAY(LONG)"),
        ("bigint_array", "ARRAY(LONG)"),
        ("float_array", "ARRAY(FLOAT)"),
        ("real_array", "ARRAY(REAL)"),
        ("numeric_array", "ARRAY(NUMERIC)"),
        ("string_array", "ARRAY(VARCHAR)"),
        ("text_array", "ARRAY(VARCHAR)"),
        ("timestamp_array", "ARRAY(TIMESTAMP WITHOUT TIME ZONE)"),
        ("timestamp without time zone_array", "ARRAY(TIMESTAMP WITHOUT TIME ZONE)"),
        ("timestamp with time zone_array", "ARRAY(TIMESTAMP WITH TIME ZONE)"),
        ("double_array", "ARRAY(DOUBLE)"),
        ("geo_point_array", "ARRAY(GEO_POINT)"),
        ("geo_shape_array", "ARRAY(GEO_SHAPE)"),
    ],
)
def test_array_type_name_renders_as_an_array_of_its_element_type(data_type, rendered):
    assert render_type(data_type) == rendered


def test_double_precision_array_renders_as_an_array_of_its_element_type():
    """
    SQLAlchemy tells `DOUBLE` and `DOUBLE PRECISION` apart from 2.0 onwards;
    before that a single stand-in covers both and renders as `DOUBLE`.
    """
    expected = "ARRAY(DOUBLE PRECISION)" if SA_VERSION >= SA_2_0 else "ARRAY(DOUBLE)"
    assert render_type("double precision_array") == expected


def test_every_mapped_type_is_the_element_of_its_array_form():
    """
    Whether an array renders is its element type's business: `float_vector`
    needs a dimension reflection cannot recover, and refuses in its array form
    exactly as it does alone, so this pins the held type rather than DDL.
    """
    dialect = CrateDialect()
    derived = {
        name: type_
        for name, type_ in TYPES_MAP.items()
        if not name.endswith(ARRAY_SUFFIX) and name + ARRAY_SUFFIX not in TYPES_MAP
    }
    assert derived
    for name, element_type in derived.items():
        resolved = dialect._resolve_type(name + ARRAY_SUFFIX)
        assert isinstance(resolved, sqltypes.ARRAY)
        assert type(resolved.item_type) is type(sqltypes.to_instance(element_type))


def test_reflected_numeric_array_refuses_ddl_without_a_precision():
    with pytest.raises(sa.exc.CompileError) as ex:
        render_ddl("numeric_array")
    assert "CrateDB stores a NUMERIC column only with a precision" in str(ex.value)


def test_reflected_object_array_keeps_its_own_type():
    assert CrateDialect()._resolve_type("object_array") is ObjectArray


@pytest.mark.parametrize(
    "data_type",
    [
        UNRESOLVABLE,
        "{0}{1}".format(UNRESOLVABLE, ARRAY_SUFFIX),
        "integer_array_array",
        "object_array_array",
        "integer_array_array_array",
    ],
)
def test_unresolved_type_refuses_ddl_and_names_the_column_type(data_type):
    """
    An unresolvable element type and an array of arrays both leave the whole
    array unresolved, and both report the array's own name, which is the one
    `information_schema` reports for that column.
    """
    with pytest.raises(sa.exc.CompileError) as ex:
        render_ddl(data_type)
    message = str(ex.value)
    assert "Unable to represent CrateDB type '{0}'".format(data_type) in message
    assert "table 't'" in message
    assert "column 'c'" in message


@pytest.mark.skipif(
    SA_VERSION < SA_1_4, reason="SQLAlchemy renders a type it has no visitor for from 1.4 onwards"
)
def test_unresolved_type_prints_its_crate_type_name():
    """
    Tools that render a reflected schema as text keep working.
    """
    type_ = CrateDialect()._resolve_type(UNRESOLVABLE)
    assert UNRESOLVABLE in str(type_)
    assert UNRESOLVABLE in str(type_.compile())
    table = sa.Table("t", sa.MetaData(), reflected_column(UNRESOLVABLE))
    assert UNRESOLVABLE in str(sa.schema.CreateTable(table))


def test_unresolved_type_remains_selectable():
    """
    One unrepresentable column does not take the whole table with it.
    """
    dialect = CrateDialect()
    table = sa.Table("t", sa.MetaData(), reflected_column(UNRESOLVABLE))
    assert "SELECT t.c" in str(table.select().compile(dialect=dialect))


@pytest.mark.parametrize(
    "data_type",
    [UNRESOLVABLE, "{0}{1}".format(UNRESOLVABLE, ARRAY_SUFFIX)],
)
def test_unresolved_type_is_logged_under_the_column_type_name(caplog, data_type):
    """
    An array is looked up through its element type, whose name belongs to no
    column, and so belongs in no trace of what the map is missing.
    """
    with caplog.at_level(logging.DEBUG, logger="sqlalchemy_cratedb.dialect"):
        CrateDialect()._resolve_type(data_type)
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "sqlalchemy_cratedb.dialect"
    ]
    assert messages == ["Unable to resolve CrateDB type: {0}".format(data_type)]


@pytest.mark.skipif(SA_VERSION < SA_1_4, reason="Test case not supported on SQLAlchemy 1.3")
def test_reflected_system_table_renders_ddl(cratedb_service):
    """
    `sys.summits` ships with every CrateDB and holds a `geo_point` column.
    """
    engine = cratedb_service.database.engine
    table = sa.Table("summits", sa.MetaData(schema="sys"), autoload_with=engine)
    ddl = str(sa.schema.CreateTable(table).compile(engine))
    assert "coordinates GEO_POINT" in ddl
