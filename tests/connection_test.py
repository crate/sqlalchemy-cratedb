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
import contextlib
import warnings
from unittest import TestCase

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import NoSuchModuleError

from sqlalchemy_cratedb import SA_1_4, SA_VERSION
from tests.util import ExtraAssertions


class SqlAlchemyConnectionTest(TestCase, ExtraAssertions):
    def test_connection_server_uri_unknown_sa_plugin(self):
        with self.assertRaises(NoSuchModuleError):
            sa.create_engine("foobar://otherhost:19201")

    def test_connection_no_hostname_no_ssl(self):
        engine = sa.create_engine("crate://")
        servers = engine.raw_connection().driver_connection.client._active_servers
        self.assertEqual(["http://127.0.0.1:4200"], servers)
        engine.dispose()

    @pytest.mark.skipif(SA_VERSION < SA_1_4, reason="Not supported by SQLAlchemy 1.3")
    def test_connection_no_hostname_with_ssl(self):
        engine = sa.create_engine("crate://?sslmode=require")
        servers = engine.raw_connection().driver_connection.client._active_servers
        self.assertEqual(["https://127.0.0.1:4200"], servers)
        engine.dispose()

    def test_connection_server_uri_http(self):
        engine = sa.create_engine("crate://otherhost:19201")
        conn = engine.raw_connection()
        self.assertEqual(
            "<Connection <Client ['http://otherhost:19201']>>", repr(conn.driver_connection)
        )
        conn.close()
        engine.dispose()

    @contextlib.contextmanager
    def verify_user_warning_about_ssl_deprecation(self):
        """
        The `ssl=true` option was flagged for deprecation. Verify that.
        """
        with warnings.catch_warnings(record=True) as w:
            # Cause all warnings to always be triggered.
            warnings.simplefilter("always")

            # Run workhorse body.
            yield

            # Verify details of the deprecation warning.
            self.assertEqual(len(w), 1)
            self.assertIsSubclass(w[-1].category, DeprecationWarning)
            self.assertIn(
                "The `ssl=true` option will be deprecated, "
                "please use `sslmode=require` going forward.",
                str(w[-1].message),
            )

    def test_connection_server_uri_https_ssl_enabled(self):
        with self.verify_user_warning_about_ssl_deprecation():
            engine = sa.create_engine("crate://otherhost:19201/?ssl=true")
            servers = engine.raw_connection().driver_connection.client._active_servers
        self.assertEqual(["https://otherhost:19201"], servers)
        engine.dispose()

    def test_connection_server_uri_https_ssl_disabled(self):
        with self.verify_user_warning_about_ssl_deprecation():
            engine = sa.create_engine("crate://otherhost:19201/?ssl=false")
            servers = engine.raw_connection().driver_connection.client._active_servers
        self.assertEqual(["http://otherhost:19201"], servers)
        engine.dispose()

    def test_connection_server_uri_https_sslmode_enabled(self):
        engine = sa.create_engine("crate://otherhost:19201/?sslmode=require")
        servers = engine.raw_connection().driver_connection.client._active_servers
        self.assertEqual(["https://otherhost:19201"], servers)
        engine.dispose()

    def test_connection_server_uri_https_sslmode_disabled(self):
        engine = sa.create_engine("crate://otherhost:19201/?sslmode=disable")
        servers = engine.raw_connection().driver_connection.client._active_servers
        self.assertEqual(["http://otherhost:19201"], servers)
        engine.dispose()

    def test_connection_server_uri_invalid_port(self):
        with self.assertRaises(ValueError) as context:
            sa.create_engine("crate://foo:bar")
        self.assertIn("invalid literal for int() with base 10: 'bar'", str(context.exception))

    def test_connection_server_uri_https_with_trusted_user(self):
        engine = sa.create_engine("crate://foo@otherhost:19201/?ssl=true")
        conn = engine.raw_connection()
        self.assertEqual(
            "<Connection <Client ['https://otherhost:19201']>>", repr(conn.driver_connection)
        )
        self.assertEqual(conn.driver_connection.client.username, "foo")
        self.assertEqual(conn.driver_connection.client.password, None)
        conn.close()
        engine.dispose()

    def test_connection_server_uri_https_with_credentials(self):
        engine = sa.create_engine("crate://foo:bar@otherhost:19201/?ssl=true")
        conn = engine.raw_connection()
        self.assertEqual(
            "<Connection <Client ['https://otherhost:19201']>>", repr(conn.driver_connection)
        )
        self.assertEqual(conn.driver_connection.client.username, "foo")
        self.assertEqual(conn.driver_connection.client.password, "bar")
        conn.close()
        engine.dispose()

    def test_connection_server_uri_parameter_timeout(self):
        engine = sa.create_engine("crate://otherhost:19201/?timeout=42.42")
        conn = engine.raw_connection()
        self.assertEqual(conn.driver_connection.client._pool_kw["timeout"], 42.42)
        conn.close()
        engine.dispose()

    def test_connection_server_uri_parameter_pool_size(self):
        engine = sa.create_engine("crate://otherhost:19201/?pool_size=20")
        conn = engine.raw_connection()
        self.assertEqual(conn.driver_connection.client._pool_kw["maxsize"], 20)
        conn.close()
        engine.dispose()

    def test_connection_multiple_server_http(self):
        engine = sa.create_engine(
            "crate://", connect_args={"servers": ["localhost:4201", "localhost:4202"]}
        )
        conn = engine.raw_connection()
        self.assertEqual(
            "<Connection <Client ['http://localhost:4201', " + "'http://localhost:4202']>>",
            repr(conn.driver_connection),
        )
        conn.close()
        engine.dispose()

    def test_connection_multiple_server_https(self):
        engine = sa.create_engine(
            "crate://",
            connect_args={
                "servers": ["localhost:4201", "localhost:4202"],
                "ssl": True,
            },
        )
        conn = engine.raw_connection()
        self.assertEqual(
            "<Connection <Client ['https://localhost:4201', " + "'https://localhost:4202']>>",
            repr(conn.driver_connection),
        )
        conn.close()
        engine.dispose()
