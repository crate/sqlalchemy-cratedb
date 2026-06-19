import base64

from sqlalchemy import String


class LargeBinary(String):
    """A type for large binary byte data.

    The :class:`.LargeBinary` type corresponds to a large and/or unlengthed
    binary type for the target platform, such as BLOB on MySQL and BYTEA for
    PostgreSQL.  It also handles the necessary conversions for the DBAPI.

    """

    __visit_name__ = "large_binary"

    def bind_processor(self, dialect):
        if dialect.dbapi is None:
            return None

        def process(value):
            if value is not None:
                return base64.b64encode(value).decode()
            else:
                return None

        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is not None:
                return base64.b64decode(value)
            return value

        return process
