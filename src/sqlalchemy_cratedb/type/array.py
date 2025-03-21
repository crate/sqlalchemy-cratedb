# -*- coding: utf-8; -*-
#
# Licensed to CRATE Technology GmbH ("Crate") under one or more contributor
# license agreements.  See the NOTICE file distributed with this work for
# additional information regarding copyright ownership.  Crate licenses
# this file to you under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.  You may
# obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
# License for the specific language governing permissions and limitations
# under the License.
#
# However, if you have executed another commercial license agreement
# with Crate these terms will supersede the license and you may use the
# software solely pursuant to the terms of the relevant commercial agreement.

# ruff: noqa: A005  # Module `array` shadows a Python standard-library module

import sqlalchemy.types as sqltypes
from sqlalchemy.ext.mutable import Mutable
from sqlalchemy.sql import default_comparator, expression, operators


class MutableList(Mutable, list):
    @classmethod
    def coerce(cls, key, value):
        """Convert plain list to MutableList"""
        if not isinstance(value, MutableList):
            if isinstance(value, list):
                return MutableList(value)
            elif value is None:
                return value
            else:
                return MutableList([value])
        else:
            return value

    def __init__(self, initval=None):
        list.__init__(self, initval or [])

    def __setitem__(self, key, value):
        list.__setitem__(self, key, value)
        self.changed()

    def __eq__(self, other):
        return list.__eq__(self, other)

    def append(self, item):
        list.append(self, item)
        self.changed()

    def insert(self, idx, item):
        list.insert(self, idx, item)
        self.changed()

    def extend(self, iterable):
        list.extend(self, iterable)
        self.changed()

    def pop(self, index=-1):
        list.pop(self, index)
        self.changed()

    def remove(self, item):
        list.remove(self, item)
        self.changed()


class Any(expression.ColumnElement):
    """Represent the clause ``left operator ANY (right)``.  ``right`` must be
    an array expression.

    copied from postgresql dialect

    .. seealso::

        :class:`sqlalchemy.dialects.postgresql.ARRAY`

        :meth:`sqlalchemy.dialects.postgresql.ARRAY.Comparator.any`
            ARRAY-bound method

    """

    __visit_name__ = "any"
    inherit_cache = True

    def __init__(self, left, right, operator=operators.eq):
        self.type = sqltypes.Boolean()
        self.left = expression.literal(left)
        self.right = right
        self.operator = operator


class _ObjectArray(sqltypes.UserDefinedType):
    cache_ok = True

    class Comparator(sqltypes.TypeEngine.Comparator):
        def __getitem__(self, key):
            return default_comparator._binary_operate(self.expr, operators.getitem, key)

        def any(self, other, operator=operators.eq):
            """Return ``other operator ANY (array)`` clause.

            Argument places are switched, because ANY requires array
            expression to be on the right hand-side.

            E.g.::

                from sqlalchemy.sql import operators

                conn.execute(
                    select([table.c.data]).where(
                            table.c.data.any(7, operator=operators.lt)
                        )
                )

            :param other: expression to be compared
            :param operator: an operator object from the
             :mod:`sqlalchemy.sql.operators`
             package, defaults to :func:`.operators.eq`.

            .. seealso::

                :class:`.postgresql.Any`

                :meth:`.postgresql.ARRAY.Comparator.all`

            """
            return Any(other, self.expr, operator=operator)

    type = MutableList
    comparator_factory = Comparator

    def get_col_spec(self, **kws):
        return "ARRAY(OBJECT)"


ObjectArray = MutableList.as_mutable(_ObjectArray)
