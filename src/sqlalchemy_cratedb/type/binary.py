import base64

from sqlalchemy import String


class BinaryBase64(String):
    """
    Emulate binary column types by base64-encoding them into a CrateDB STRING.

    CrateDB has no binary data type, so `sa.LargeBinary`, `sa.BLOB`,
    `sa.BINARY` and `sa.VARBINARY` are stored as base64 text.
    """

    __visit_name__ = "large_binary"

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            return base64.b64encode(value).decode()

        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            return base64.b64decode(value)

        return process
