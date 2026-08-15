import warnings

from sqlalchemy import types as sqltypes
from sqlalchemy.ext.mutable import Mutable


class MutableDict(Mutable, dict):
    @classmethod
    def coerce(cls, key, value):
        "Convert plain dictionaries to MutableDict."

        if not isinstance(value, MutableDict):
            if isinstance(value, dict):
                return MutableDict(value)

            # this call will raise ValueError
            return Mutable.coerce(key, value)
        else:
            return value

    def __init__(self, initval=None, to_update=None, root_change_key=None):
        initval = initval or {}
        self._changed_keys = set()
        self._deleted_keys = set()
        self._overwrite_key = root_change_key
        self.to_update = self if to_update is None else to_update
        for k in initval:
            initval[k] = self._convert_dict(
                initval[k], overwrite_key=k if self._overwrite_key is None else self._overwrite_key
            )
        dict.__init__(self, initval)

    def __setitem__(self, key, value):
        value = self._convert_dict(
            value, key if self._overwrite_key is None else self._overwrite_key
        )
        dict.__setitem__(self, key, value)
        self.to_update.on_key_changed(key if self._overwrite_key is None else self._overwrite_key)

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        # add the key to the deleted keys if this is the root object
        # otherwise update on root object
        if self._overwrite_key is None:
            self._deleted_keys.add(key)
            self.changed()
        else:
            self.to_update.on_key_changed(self._overwrite_key)

    def on_key_changed(self, key):
        self._deleted_keys.discard(key)
        self._changed_keys.add(key)
        self.changed()

    def _convert_dict(self, value, overwrite_key):
        if isinstance(value, dict) and not isinstance(value, MutableDict):
            return MutableDict(value, self.to_update, overwrite_key)
        return value

    def __eq__(self, other):
        return dict.__eq__(self, other)


class ObjectTypeImpl(sqltypes.UserDefinedType, sqltypes.JSON):
    __visit_name__ = "OBJECT"

    cache_ok = False
    none_as_null = False


# Designated name to refer to. `Object` is too ambiguous.
ObjectType = MutableDict.as_mutable(ObjectTypeImpl)

# Backward-compatibility aliases.
_deprecated_Craty = ObjectType
_deprecated_Object = ObjectType

# https://www.lesinskis.com/deprecating-module-scope-variables.html
deprecated_names = ["Craty", "Object"]


def __getattr__(name):
    if name in deprecated_names:
        warnings.warn(
            f"{name} is deprecated and will be removed in future releases. "
            f"Please use ObjectType instead.",
            category=DeprecationWarning,
            stacklevel=2,
        )
        return globals()[f"_deprecated_{name}"]
    raise AttributeError(f"module {__name__} has no attribute {name}")


__all__ = deprecated_names + ["ObjectType"]
