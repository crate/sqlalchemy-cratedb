import itertools
import typing as t

import sqlalchemy as sa

if t.TYPE_CHECKING:
    try:
        from sqlalchemy.orm import DeclarativeBase
    except ImportError:
        pass


def refresh_table(connection, target: t.Union[str, "DeclarativeBase"]):
    """
    Invoke a `REFRESH TABLE` statement.
    """
    if hasattr(target, "__tablename__"):
        sql = f"REFRESH TABLE {target.__tablename__}"
    else:
        sql = f"REFRESH TABLE {target}"
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
