import ipaddress

from sqlalchemy import types as sqltypes


class IP(sqltypes.UserDefinedType):
    cache_ok = True

    def get_col_spec(self):
        return "IP"

    def bind_processor(self, dialect):
        def process(value):
            if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
                return str(value)
            return value

        return process

    @property
    def python_type(self):
        return str
