import datetime
import ipaddress

import pytest
import sqlalchemy as sa
from sqlalchemy import types as sqltypes

from sqlalchemy_cratedb import IP, Geopoint, Geoshape, ObjectArray
from sqlalchemy_cratedb.dialect import ARRAY_SUFFIX, TYPES_MAP, CrateDialect
from sqlalchemy_cratedb.sa_version import SA_2_0, SA_VERSION

UNRESOLVABLE = "unresolvable_cratedb_type"


def reflected_column(data_type):
    return sa.Column("c", CrateDialect()._resolve_type(data_type))


def render_type(data_type):
    dialect = CrateDialect()
    return dialect.type_compiler.process(sqltypes.to_instance(dialect._resolve_type(data_type)))


def render_ddl(data_type):
    dialect = CrateDialect()
    table = sa.Table("t", sa.MetaData(), reflected_column(data_type))
    return str(sa.schema.CreateTable(table).compile(dialect=dialect))


def render_row_ddl(row):
    dialect = CrateDialect()
    column = dialect._create_column_info(row)
    table = sa.Table("t", sa.MetaData(), sa.Column(column["name"], column["type"]))
    return str(sa.schema.CreateTable(table).compile(dialect=dialect))


@pytest.mark.parametrize(
    ("data_type", "rendered"),
    [
        ("geo_point", "GEO_POINT"),
        ("geo_shape", "GEO_SHAPE"),
        ("ip", "IP"),
        ("character", "CHAR"),
    ],
)
def test_reflected_column_renders_its_ddl(data_type, rendered):
    assert "c {0}".format(rendered) in render_ddl(data_type)


def test_reflected_geo_column_resolves_to_the_geo_type():
    dialect = CrateDialect()
    assert dialect._resolve_type("geo_point") is Geopoint
    assert dialect._resolve_type("geo_shape") is Geoshape


@pytest.mark.parametrize(
    ("row", "rendered"),
    [
        (("c", "character", 5, None, None), "c CHAR(5)"),
        (("c", "text", 10, None, None), "c VARCHAR(10)"),
        (("c", "text", None, None, None), "c VARCHAR"),
    ],
)
def test_reflected_string_column_keeps_its_length(row, rendered):
    assert "\t{0}\n".format(rendered) in render_row_ddl(row)


@pytest.mark.parametrize(
    ("row", "rendered"),
    [
        (("c", "numeric", None, 10, 2), "c NUMERIC(10, 2)"),
        # CrateDB reports a declared `NUMERIC(5)` with a scale of zero.
        (("c", "numeric", None, 5, 0), "c NUMERIC(5, 0)"),
    ],
)
def test_reflected_numeric_column_renders_its_precision_and_scale(row, rendered):
    assert "\t{0}\n".format(rendered) in render_row_ddl(row)


@pytest.mark.parametrize(
    "row",
    [
        # CrateDB before 6.4.6 reports no scale. An unknown scale is not zero:
        # `NUMERIC(10)` would drop the decimals of a table created from it.
        ("c", "numeric", None, 10, None),
        ("c", "numeric", None, None, None),
    ],
)
def test_reflected_numeric_column_without_both_values_has_no_precision(row):
    # Unlike its neighbours, this test checks the rendered type, not the DDL from
    # `render_row_ddl`. A bare `NUMERIC` has no valid DDL: CrateDB refuses to store a
    # NUMERIC column without a precision, so `CrateDDLCompiler` raises `CompileError`
    # before rendering any text. Asserting that error would test the existing guard,
    # not this reflection. Rendering the DDL with another dialect, which lacks the
    # guard, would test DDL this dialect never emits. The type compiler accepts a bare
    # `NUMERIC`, a valid cast target, so it shows what reflection produced: the exact
    # match rules out `NUMERIC(10)` and `NUMERIC(10, 0)`.
    dialect = CrateDialect()
    column = dialect._create_column_info(row)
    assert dialect.type_compiler.process(sqltypes.to_instance(column["type"])) == "NUMERIC"


def test_reflected_integer_column_ignores_its_reported_precision():
    # The precision of an integer is its bit width, fixed by the type.
    assert "\tc INT\n" in render_row_ddl(("c", "integer", None, 32, 0))


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
        ("ip_array", "ARRAY(IP)"),
    ],
)
def test_array_type_name_renders_as_an_array_of_its_element_type(data_type, rendered):
    assert render_type(data_type) == rendered


def test_double_precision_array_renders_as_an_array_of_its_element_type():
    expected = "ARRAY(DOUBLE PRECISION)" if SA_VERSION >= SA_2_0 else "ARRAY(DOUBLE)"
    assert render_type("double precision_array") == expected


def test_every_mapped_type_is_the_element_of_its_array_form():
    # Pins the held type rather than DDL, which `float_vector` refuses without its dimension.
    dialect = CrateDialect()
    derived = {
        name: type_
        for name, type_ in TYPES_MAP.items()
        if not name.endswith(ARRAY_SUFFIX)
        and name + ARRAY_SUFFIX not in TYPES_MAP
        and name != "character"
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
        "character_array",
    ],
)
def test_unresolved_type_refuses_ddl_and_names_the_column_type(data_type):
    with pytest.raises(sa.exc.CompileError) as ex:
        render_ddl(data_type)
    message = str(ex.value)
    assert "Unable to represent CrateDB type '{0}'".format(data_type) in message
    assert "table 't'" in message
    assert "column 'c'" in message


def test_unresolved_type_prints_its_crate_type_name():
    type_ = CrateDialect()._resolve_type(UNRESOLVABLE)
    assert UNRESOLVABLE in str(type_)
    assert UNRESOLVABLE in str(type_.compile())
    table = sa.Table("t", sa.MetaData(), reflected_column(UNRESOLVABLE))
    assert UNRESOLVABLE in str(sa.schema.CreateTable(table))


def test_reflected_unknown_type_warns_with_the_column_name():
    with pytest.warns(sa.exc.SAWarning, match="type '{0}' of column 'c'".format(UNRESOLVABLE)):
        column = CrateDialect()._create_column_info(("c", UNRESOLVABLE, None, None, None))
    assert isinstance(column["type"], sqltypes.NullType)


def test_unresolved_type_binds_a_compared_value_by_its_python_type():
    table = sa.Table("t", sa.MetaData(), reflected_column(UNRESOLVABLE))
    comparison = table.c.c == datetime.datetime(2026, 1, 1)
    assert isinstance(comparison.right.type, sqltypes.DateTime)


def test_unresolved_type_remains_selectable():
    dialect = CrateDialect()
    table = sa.Table("t", sa.MetaData(), reflected_column(UNRESOLVABLE))
    assert "SELECT t.c" in str(table.select().compile(dialect=dialect))


def test_reflected_system_table_renders_ddl(cratedb_service):
    engine = cratedb_service.engine
    table = sa.Table("summits", sa.MetaData(schema="sys"), autoload_with=engine)
    ddl = str(sa.schema.CreateTable(table).compile(engine))
    assert "coordinates GEO_POINT" in ddl


def test_reflected_table_renders_string_lengths_and_ip(cratedb_service):
    engine = cratedb_service.engine
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS reflected_strings")
        connection.exec_driver_sql(
            "CREATE TABLE reflected_strings (code CHAR(5), name VARCHAR(10), address IP)"
        )
    table = sa.Table("reflected_strings", sa.MetaData(), autoload_with=engine)
    ddl = str(sa.schema.CreateTable(table).compile(engine))
    assert "code CHAR(5)" in ddl
    assert "name VARCHAR(10)" in ddl
    assert "address IP" in ddl


def test_reflected_table_renders_numeric_precision_and_scale(cratedb_service):
    engine = cratedb_service.engine
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS reflected_numerics")
        connection.exec_driver_sql(
            "CREATE TABLE reflected_numerics (amount NUMERIC(10, 2), rate NUMERIC(5))"
        )
        connection.exec_driver_sql("INSERT INTO reflected_numerics (amount) VALUES (1.25)")
        connection.exec_driver_sql("REFRESH TABLE reflected_numerics")
    table = sa.Table("reflected_numerics", sa.MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        amount = connection.execute(sa.select(table.c.amount)).scalar()
        server_version_info = connection.dialect.server_version_info

    if server_version_info >= (6, 4, 6):
        ddl = str(sa.schema.CreateTable(table).compile(engine))
        assert "amount NUMERIC(10, 2)" in ddl
        assert "rate NUMERIC(5, 0)" in ddl
        assert str(amount) == "1.25"
    else:
        # Older servers report no scale, so the columns carry no precision. Such a
        # table has no valid DDL; see the unit test for reflection without both values.
        type_compiler = engine.dialect.type_compiler
        assert type_compiler.process(table.c.amount.type) == "NUMERIC"
        assert type_compiler.process(table.c.rate.type) == "NUMERIC"


def test_ip_column_stores_ipaddress_objects(cratedb_service):
    engine = cratedb_service.engine
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS ip_addresses")
        connection.exec_driver_sql("CREATE TABLE ip_addresses (address IP)")
    table = sa.Table("ip_addresses", sa.MetaData(), sa.Column("address", IP))
    values = ["10.0.0.1", ipaddress.IPv4Address("10.0.0.2"), ipaddress.IPv6Address("::1")]
    with engine.begin() as connection:
        connection.execute(table.insert(), [{"address": value} for value in values])
        connection.exec_driver_sql("REFRESH TABLE ip_addresses")
        stored = connection.execute(sa.select(table.c.address)).scalars().all()
    assert sorted(stored) == ["10.0.0.1", "10.0.0.2", "::1"]
