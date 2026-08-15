import enum

from sqlalchemy.util import classproperty


class SSLMode(enum.IntEnum):
    """
    SSLMode class from asyncpg, with a little improvement.
    https://github.com/MagicStack/asyncpg/blob/v0.31.0/asyncpg/connect_utils.py#L36-L48
    """

    disable = 0
    allow = 1
    prefer = 2
    require = 3
    verify_ca = 4
    verify_full = 5

    @classmethod
    def parse(cls, sslmode):
        if isinstance(sslmode, cls):
            return sslmode
        return getattr(cls, sslmode.replace("-", "_"))

    @classproperty
    def modes(cls):
        return [m.name.replace("_", "-") for m in cls]
