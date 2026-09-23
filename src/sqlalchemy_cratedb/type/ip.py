from sqlalchemy import types as sqltypes


class IP(sqltypes.UserDefinedType):
    cache_ok = True

    def get_col_spec(self):
        return "IP"

    @property
    def python_type(self):
        return str
