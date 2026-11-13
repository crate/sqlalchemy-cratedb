import geojson
from sqlalchemy import types as sqltypes
from sqlalchemy.sql import default_comparator, operators


class Geopoint(sqltypes.UserDefinedType):
    cache_ok = True

    class Comparator(sqltypes.TypeEngine.Comparator):
        def __getitem__(self, key):
            return default_comparator._binary_operate(self.expr, operators.getitem, key)

    def get_col_spec(self):
        return "GEO_POINT"

    def bind_processor(self, dialect):
        def process(value):
            if isinstance(value, geojson.Point):
                return value.coordinates
            return value

        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            return tuple(value)

        return process

    comparator_factory = Comparator


class Geoshape(sqltypes.UserDefinedType):
    cache_ok = True

    class Comparator(sqltypes.TypeEngine.Comparator):
        def __getitem__(self, key):
            return default_comparator._binary_operate(self.expr, operators.getitem, key)

    def get_col_spec(self):
        return "GEO_SHAPE"

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            return geojson.GeoJSON.to_instance(value)

        return process

    comparator_factory = Comparator
