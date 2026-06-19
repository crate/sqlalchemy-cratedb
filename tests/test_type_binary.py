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

import base64
from unittest import TestCase
from unittest.mock import MagicMock

from sqlalchemy_cratedb.type.binary import LargeBinary


class LargeBinaryBindProcessorTest(TestCase):
    def setUp(self):
        self.type = LargeBinary()
        self.dialect = MagicMock()
        self.dialect.dbapi = MagicMock()

    def test_encodes_bytes_to_base64_string(self):
        process = self.type.bind_processor(self.dialect)
        result = process(b"hello world")
        self.assertEqual(result, base64.b64encode(b"hello world").decode())

    def test_returns_none_for_none_input(self):
        process = self.type.bind_processor(self.dialect)
        self.assertIsNone(process(None))

    def test_returns_none_processor_when_dbapi_is_none(self):
        self.dialect.dbapi = None
        processor = self.type.bind_processor(self.dialect)
        self.assertIsNone(processor)

    def test_encodes_arbitrary_binary_data(self):
        process = self.type.bind_processor(self.dialect)
        data = bytes(range(256))
        result = process(data)
        self.assertEqual(result, base64.b64encode(data).decode())


class LargeBinaryResultProcessorTest(TestCase):
    def setUp(self):
        self.type = LargeBinary()
        self.dialect = MagicMock()

    def test_decodes_base64_string_to_bytes(self):
        process = self.type.result_processor(self.dialect, None)
        encoded = base64.b64encode(b"hello world").decode()
        result = process(encoded)
        self.assertEqual(result, b"hello world")

    def test_returns_none_for_none_input(self):
        process = self.type.result_processor(self.dialect, None)
        self.assertIsNone(process(None))

    def test_round_trip(self):
        bind = self.type.bind_processor(self.dialect)
        result = self.type.result_processor(self.dialect, None)
        data = b"\x00\x01\x02\xff\xfe\xfd"
        self.assertEqual(result(bind(data)), data)
