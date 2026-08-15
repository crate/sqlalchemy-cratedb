import pytest

from sqlalchemy_cratedb.support import quote_relation_name


def test_quote_relation_name_once():
    """
    Verify quoting a simple or full-qualified relation name.
    """

    # Table name only.
    assert quote_relation_name("my_table") == "my_table"
    assert quote_relation_name("my-table") == '"my-table"'
    assert quote_relation_name("MyTable") == '"MyTable"'
    assert quote_relation_name('"MyTable"') == '"MyTable"'

    # Schema and table name.
    assert quote_relation_name("my_schema.my_table") == "my_schema.my_table"
    assert quote_relation_name("my-schema.my_table") == '"my-schema".my_table'
    assert quote_relation_name('"wrong-quoted-fqn.my_table"') == '"wrong-quoted-fqn.my_table"'
    assert quote_relation_name('"my_schema"."my_table"') == '"my_schema"."my_table"'

    # Catalog, schema, and table name.
    assert quote_relation_name("crate.doc.t01") == "crate.doc.t01"


def test_quote_relation_name_twice():
    """
    Verify quoting a relation name twice does not cause any harm.
    """
    input_fqn = "foo-bar.baz_qux"
    output_fqn = '"foo-bar".baz_qux'
    assert quote_relation_name(input_fqn) == output_fqn
    assert quote_relation_name(output_fqn) == output_fqn


def test_quote_relation_name_reserved_keywords():
    """
    Verify quoting a simple relation name that is a reserved keyword.
    """
    assert quote_relation_name("table") == '"table"'
    assert quote_relation_name("true") == '"true"'
    assert quote_relation_name("select") == '"select"'


def test_quote_relation_name_with_invalid_fqn():
    """
    Verify quoting a relation name with an invalid fqn raises an error.
    """
    with pytest.raises(ValueError):
        quote_relation_name("too-many.my-db.my-schema.my-table")
