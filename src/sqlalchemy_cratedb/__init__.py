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

from .dialect import dialect
from .predicate import match
from .sa_version import SA_1_4, SA_2_0, SA_VERSION  # noqa: F401  # Re-exported for compatibility.
from .support import insert_bulk
from .type.array import ObjectArray
from .type.geo import Geopoint, Geoshape
from .type.ip import IP
from .type.object import ObjectType
from .type.unresolved import UnresolvedType
from .type.vector import FloatVector, knn_match

if SA_VERSION < SA_2_0:
    import textwrap
    import warnings

    SA14_DEPRECATION_WARNING = textwrap.dedent(
        """
    WARNING: SQLAlchemy 1.4 is EOL.

    SQLAlchemy 1.4 is no longer maintained, its last release was 1.4.54 in September 2024.
    Future versions of the CrateDB SQLAlchemy dialect will drop support for SQLAlchemy 1.4.
    It is recommended that you transition to using SQLAlchemy 2.0 or later:

    - https://docs.sqlalchemy.org/en/20/changelog/migration_20.html
    """.lstrip("\n")
    )
    warnings.warn(message=SA14_DEPRECATION_WARNING, category=DeprecationWarning, stacklevel=2)

try:
    from importlib.metadata import PackageNotFoundError, version
except (ImportError, ModuleNotFoundError):  # pragma:nocover
    from importlib_metadata import (  # type: ignore[assignment,no-redef,unused-ignore]
        PackageNotFoundError,
        version,
    )

try:
    __version__ = version("sqlalchemy-cratedb")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"


__all__ = [
    __version__,
    dialect,
    FloatVector,
    Geopoint,
    Geoshape,
    IP,
    ObjectArray,
    ObjectType,
    UnresolvedType,
    match,
    knn_match,
    insert_bulk,
]
