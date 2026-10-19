# Copyright (c) 2021-2023, Crate.io Inc.
# Distributed under the terms of the AGPLv3 license, see LICENSE.
import os

import pytest

from tests.util import CrateDBTestAdapter

# Use different schemas for storing the subsystem database tables, and the
# test/example data, so that they do not accidentally touch the default `doc`
# schema.
TESTDRIVE_EXT_SCHEMA = "testdrive-ext"
TESTDRIVE_DATA_SCHEMA = "testdrive-data"


@pytest.fixture(scope="session")
def cratedb_service():
    """
    Provide a CrateDB service instance to the test suite.
    """
    db = CrateDBTestAdapter(os.environ.get("CRATEDB_VERSION", "nightly"))
    try:
        db.start()
        yield db
    finally:
        db.stop()
