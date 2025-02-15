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

import string
import warnings
from collections import defaultdict

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql.base import RESERVED_WORDS as POSTGRESQL_RESERVED_WORDS
from sqlalchemy.dialects.postgresql.base import PGCompiler
from sqlalchemy.sql import compiler
from sqlalchemy.types import String

from .sa_version import SA_1_4, SA_VERSION
from .type.geo import Geopoint, Geoshape
from .type.object import MutableDict, ObjectTypeImpl


def rewrite_update(clauseelement, multiparams, params):
    """change the params to enable partial updates

    sqlalchemy by default only supports updates of complex types in the form of

        "col = ?", ({"x": 1, "y": 2}

    but crate supports

        "col['x'] = ?, col['y'] = ?", (1, 2)

    by using the `ObjectType` (`MutableDict`) type.
    The update statement is only rewritten if an item of the MutableDict was
    changed.
    """
    newmultiparams = []
    _multiparams = multiparams[0]
    if len(_multiparams) == 0:
        return clauseelement, multiparams, params
    for _params in _multiparams:
        newparams = {}
        for key, val in _params.items():
            if not isinstance(val, MutableDict) or (
                not any(val._changed_keys) and not any(val._deleted_keys)
            ):
                newparams[key] = val
                continue

            for subkey, subval in val.items():
                if subkey in val._changed_keys:
                    newparams["{0}['{1}']".format(key, subkey)] = subval
            for subkey in val._deleted_keys:
                newparams["{0}['{1}']".format(key, subkey)] = None
        newmultiparams.append(newparams)
    _multiparams = (newmultiparams,)
    clause = clauseelement.values(newmultiparams[0])
    clause._crate_specific = True
    return clause, _multiparams, params


@sa.event.listens_for(sa.engine.Engine, "before_execute", retval=True)
def crate_before_execute(conn, clauseelement, multiparams, params, *args, **kwargs):
    is_crate = type(conn.dialect).__name__ == "CrateDialect"
    if is_crate and isinstance(clauseelement, sa.sql.expression.Update):
        if SA_VERSION >= SA_1_4:
            if params is None:
                multiparams = ([],)
            else:
                multiparams = ([params],)
            params = {}

        clauseelement, multiparams, params = rewrite_update(clauseelement, multiparams, params)

        if SA_VERSION >= SA_1_4:
            if multiparams[0]:
                params = multiparams[0][0]
            else:
                params = multiparams[0]
            multiparams = []

    return clauseelement, multiparams, params


class CrateDDLCompiler(compiler.DDLCompiler):
    __special_opts_tmpl = {"partitioned_by": " PARTITIONED BY ({0})"}
    __clustered_opts_tmpl = {
        "number_of_shards": " INTO {0} SHARDS",
        "clustered_by": " BY ({0})",
    }
    __clustered_opt_tmpl = " CLUSTERED{clustered_by}{number_of_shards}"

    def get_column_specification(self, column, **kwargs):
        colspec = (
            self.preparer.format_column(column)
            + " "
            + self.dialect.type_compiler.process(column.type)
        )

        default = self.get_column_default_string(column)
        if default is not None:
            colspec += " DEFAULT " + default

        if column.computed is not None:
            colspec += " " + self.process(column.computed)

        if column.nullable is False:
            colspec += " NOT NULL"
        elif column.nullable and column.primary_key:
            raise sa.exc.CompileError("Primary key columns cannot be nullable")

        if column.dialect_options["crate"].get("index") is False:
            if isinstance(column.type, (Geopoint, Geoshape, ObjectTypeImpl)):
                raise sa.exc.CompileError(
                    "Disabling indexing is not supported for column "
                    "types OBJECT, GEO_POINT, and GEO_SHAPE"
                )

            colspec += " INDEX OFF"

        if column.dialect_options["crate"].get("columnstore") is False:
            if not isinstance(column.type, (String,)):
                raise sa.exc.CompileError(
                    "Controlling the columnstore is only allowed for STRING columns"
                )

            colspec += " STORAGE WITH (columnstore = false)"

        return colspec

    def visit_computed_column(self, generated):
        if generated.persisted is False:
            raise sa.exc.CompileError(
                "Virtual computed columns are not supported, set 'persisted' to None or True"
            )

        return "GENERATED ALWAYS AS (%s)" % self.sql_compiler.process(
            generated.sqltext, include_table=False, literal_binds=True
        )

    def post_create_table(self, table):
        special_options = ""
        clustered_options = defaultdict(str)
        table_opts = []

        opts = dict(
            (k[len(self.dialect.name) + 1 :], v)
            for k, v in table.kwargs.items()
            if k.startswith("%s_" % self.dialect.name)
        )
        for k, v in opts.items():
            if k in self.__special_opts_tmpl:
                special_options += self.__special_opts_tmpl[k].format(v)
            elif k in self.__clustered_opts_tmpl:
                clustered_options[k] = self.__clustered_opts_tmpl[k].format(v)
            else:
                table_opts.append("{0} = {1}".format(k, v))
        if clustered_options:
            special_options += string.Formatter().vformat(
                self.__clustered_opt_tmpl, (), clustered_options
            )
        if table_opts:
            return special_options + " WITH ({0})".format(", ".join(sorted(table_opts)))
        return special_options

    def visit_foreign_key_constraint(self, constraint, **kw):
        """
        CrateDB does not support foreign key constraints.
        """
        warnings.warn(
            "CrateDB does not support foreign key constraints, "
            "they will be omitted when generating DDL statements.",
            stacklevel=2,
        )
        return

    def visit_unique_constraint(self, constraint, **kw):
        """
        CrateDB does not support unique key constraints.
        """
        warnings.warn(
            "CrateDB does not support unique constraints, "
            "they will be omitted when generating DDL statements.",
            stacklevel=2,
        )
        return


class CrateTypeCompiler(compiler.GenericTypeCompiler):
    def visit_string(self, type_, **kw):
        return "STRING"

    def visit_unicode(self, type_, **kw):
        return "STRING"

    def visit_TEXT(self, type_, **kw):
        return "STRING"

    def visit_DECIMAL(self, type_, **kw):
        return "DOUBLE"

    def visit_BIGINT(self, type_, **kw):
        return "LONG"

    def visit_NUMERIC(self, type_, **kw):
        return "LONG"

    def visit_INTEGER(self, type_, **kw):
        return "INT"

    def visit_SMALLINT(self, type_, **kw):
        return "SHORT"

    def visit_datetime(self, type_, **kw):
        return self.visit_TIMESTAMP(type_, **kw)

    def visit_date(self, type_, **kw):
        return "TIMESTAMP"

    def visit_ARRAY(self, type_, **kw):
        if type_.dimensions is not None and type_.dimensions > 1:
            raise NotImplementedError("CrateDB doesn't support multidimensional arrays")
        return "ARRAY({0})".format(self.process(type_.item_type))

    def visit_OBJECT(self, type_, **kw):
        return "OBJECT"

    def visit_FLOAT_VECTOR(self, type_, **kw):
        dimensions = type_.dimensions
        if dimensions is None:
            raise ValueError("FloatVector must be initialized with dimension size")
        return f"FLOAT_VECTOR({dimensions})"

    def visit_TIMESTAMP(self, type_, **kw):
        """
        Support for `TIMESTAMP WITH|WITHOUT TIME ZONE`.

        From `sqlalchemy.dialects.postgresql.base.PGTypeCompiler`.
        """
        return "TIMESTAMP %s" % ((type_.timezone and "WITH" or "WITHOUT") + " TIME ZONE",)


class CrateCompiler(compiler.SQLCompiler):
    def visit_getitem_binary(self, binary, operator, **kw):
        return "{0}['{1}']".format(self.process(binary.left, **kw), binary.right.value)

    def visit_json_getitem_op_binary(self, binary, operator, _cast_applied=False, **kw):
        return "{0}['{1}']".format(self.process(binary.left, **kw), binary.right.value)

    def visit_any(self, element, **kw):
        return "%s%sANY (%s)" % (
            self.process(element.left, **kw),
            compiler.OPERATORS[element.operator],
            self.process(element.right, **kw),
        )

    def visit_ilike_case_insensitive_operand(self, element, **kw):
        """
        Use native `ILIKE` operator, like PostgreSQL's `PGCompiler`.
        """
        if self.dialect.has_ilike_operator():
            return element.element._compiler_dispatch(self, **kw)
        else:
            return super().visit_ilike_case_insensitive_operand(element, **kw)

    def visit_ilike_op_binary(self, binary, operator, **kw):
        """
        Use native `ILIKE` operator, like PostgreSQL's `PGCompiler`.

        Do not implement the `ESCAPE` functionality, because it is not
        supported by CrateDB.
        """
        if binary.modifiers.get("escape", None) is not None:
            raise NotImplementedError("Unsupported feature: ESCAPE is not supported")
        if self.dialect.has_ilike_operator():
            return "%s ILIKE %s" % (
                self.process(binary.left, **kw),
                self.process(binary.right, **kw),
            )
        else:
            return super().visit_ilike_op_binary(binary, operator, **kw)

    def visit_not_ilike_op_binary(self, binary, operator, **kw):
        """
        Use native `ILIKE` operator, like PostgreSQL's `PGCompiler`.

        Do not implement the `ESCAPE` functionality, because it is not
        supported by CrateDB.
        """
        if binary.modifiers.get("escape", None) is not None:
            raise NotImplementedError("Unsupported feature: ESCAPE is not supported")
        if self.dialect.has_ilike_operator():
            return "%s NOT ILIKE %s" % (
                self.process(binary.left, **kw),
                self.process(binary.right, **kw),
            )
        else:
            return super().visit_not_ilike_op_binary(binary, operator, **kw)

    def limit_clause(self, select, **kw):
        """
        Generate OFFSET / LIMIT clause, PostgreSQL-compatible.
        """
        return PGCompiler.limit_clause(self, select, **kw)

    def for_update_clause(self, select, **kw):
        # CrateDB does not support the `INSERT ... FOR UPDATE` clause.
        # See https://github.com/crate/crate-python/issues/577.
        warnings.warn(
            "CrateDB does not support the 'INSERT ... FOR UPDATE' clause, "
            "it will be omitted when generating SQL statements.",
            stacklevel=2,
        )
        return ""


CRATEDB_RESERVED_WORDS = (
    "add, alter, between, by, called, costs, delete, deny, directory, drop, escape, exists, "
    "extract, first, function, if, index, input, insert, last, match, nulls, object, "
    "persistent, recursive, reset, returns, revoke, set, stratify, transient, try_cast, "
    "unbounded, update".split(", ")
)


class CrateIdentifierPreparer(sa.sql.compiler.IdentifierPreparer):
    """
    Define CrateDB's reserved words to be quoted properly.
    """

    reserved_words = set(list(POSTGRESQL_RESERVED_WORDS) + CRATEDB_RESERVED_WORDS)

    def _unquote_identifier(self, value):
        if value[0] == self.initial_quote:
            value = value[1:-1].replace(self.escape_to_quote, self.escape_quote)
        return value

    def format_type(self, type_, use_schema=True):
        if not type_.name:
            raise sa.exc.CompileError("Type requires a name.")

        name = self.quote(type_.name)
        effective_schema = self.schema_for_object(type_)

        if not self.omit_schema and use_schema and effective_schema is not None:
            name = self.quote_schema(effective_schema) + "." + name
        return name
