# Copyright (c) 2021-2023, Crate.io Inc.
# Distributed under the terms of the AGPLv3 license, see LICENSE.
import os
from pathlib import Path

import pytest
from crate.client.http import Client
from cratedb_toolkit.testing.testcontainers.cratedb import CrateDBTestAdapter

# Use different schemas for storing the subsystem database tables, and the
# test/example data, so that they do not accidentally touch the default `doc`
# schema.
TESTDRIVE_EXT_SCHEMA = "testdrive-ext"
TESTDRIVE_DATA_SCHEMA = "testdrive-data"

CRATEDB_VERSION = os.environ.get("CRATEDB_VERSION", "latest")
ASSETS_PATH = Path(__file__).parent / "assets"
OFFLINE_SERVER_VERSION = "6.5.0"
DEFAULT_SERVERS = {"http://127.0.0.1:4200", "http://localhost:4200"}


@pytest.fixture(scope="session")
def cratedb_service():
    """
    Provide a CrateDB service instance to the test suite.
    """
    db = CrateDBTestAdapter(crate_version=CRATEDB_VERSION)
    db.start(volumes=[(str(ASSETS_PATH), "/assets", "ro")])
    yield db
    db.stop()


@pytest.fixture(scope="session")
def crate_host(cratedb_service):
    """
    Provide the `host:port` address of CrateDB's HTTP interface.
    """
    container = cratedb_service.cratedb
    return "{host}:{port}".format(
        host=container.get_container_host_ip(),
        port=container.get_exposed_port(container.port_to_expose),
    )


@pytest.fixture(autouse=True)
def offline_default_server(monkeypatch):
    """
    Answer the server version probe for the default address `localhost:4200`.
    """
    probe = Client.server_infos

    def server_infos(self, server):
        if server in DEFAULT_SERVERS:
            return server, "crate", OFFLINE_SERVER_VERSION
        return probe(self, server)

    monkeypatch.setattr(Client, "server_infos", server_infos)
