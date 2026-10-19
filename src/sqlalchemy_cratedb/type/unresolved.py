from sqlalchemy import types as sqltypes


class UnresolvedType(sqltypes.NullType):
    __visit_name__ = "unresolved"

    cache_ok = True

    def __init__(self, type_name):
        self.type_name = type_name
