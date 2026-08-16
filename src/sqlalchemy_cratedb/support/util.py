import itertools
import typing as t

import sqlalchemy as sa

from sqlalchemy_cratedb.dialect import CrateDialect

if t.TYPE_CHECKING:
    try:
        from sqlalchemy.orm import DeclarativeBase
    except ImportError:
        pass


# An instance of the dialect used for quoting purposes.
identifier_preparer = CrateDialect().identifier_preparer


def refresh_table(
    connection, target: t.Union[str, "DeclarativeBase", "sa.sql.selectable.TableClause"]
):
    """
    Invoke a `REFRESH TABLE` statement.
    """

    if isinstance(target, sa.sql.selectable.TableClause):
        full_table_name = f'"{target.name}"'
        if target.schema is not None:
            full_table_name = f'"{target.schema}".' + full_table_name
    elif hasattr(target, "__tablename__"):
        full_table_name = target.__tablename__
    else:
        full_table_name = target

    sql = f"REFRESH TABLE {full_table_name}"
    connection.execute(sa.text(sql))


def refresh_dirty(session, flush_context=None):
    """
    Invoke a `REFRESH TABLE` statement on each table entity flagged as "dirty".

    SQLAlchemy event handler for the 'after_flush' event,
    invoking `REFRESH TABLE` on each table which has been modified.
    """
    dirty_entities = itertools.chain(session.new, session.dirty, session.deleted)
    dirty_classes = {entity.__class__ for entity in dirty_entities}
    for class_ in dirty_classes:
        refresh_table(session, class_)


def quote_relation_name(ident: str) -> str:
    """
    Quote a simple or full-qualified table/relation name, when needed.

    Simple:         <table>
    Full-qualified: <schema>.<table>

    Happy path examples:

        foo => foo
        Foo => "Foo"
        "Foo" => "Foo"
        foo.bar => foo.bar
        foo-bar.baz_qux => "foo-bar".baz_qux

    Such input strings will not be modified:

        "foo.bar" => "foo.bar"
    """

    # If a quote exists at the beginning or the end of the input string,
    # let's consider that the relation name has been quoted already.
    if ident.startswith('"') or ident.endswith('"'):
        return ident

    # If a dot is included, it's a full-qualified identifier like <schema>.<table>.
    # It needs to be split, in order to apply identifier quoting properly.
    parts = ident.split(".")
    if len(parts) > 3:
        raise ValueError(f"Invalid relation name, too many parts: {ident}")
    return ".".join(map(identifier_preparer.quote, parts))
