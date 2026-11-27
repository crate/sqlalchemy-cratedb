import asyncio
import functools
import os
import socket
import time
from typing import Callable, Dict, Optional, Tuple

CLIENT_TIMEOUT_MESSAGE = "client_timeout ({} s) expired: connection closed by the client"

# As crate-python's retry interval for a server that failed.
HOST_COOLDOWN_SECONDS = 30.0


@functools.lru_cache(maxsize=None)
def client_timeout_error():
    """
    The error raised when `client_timeout` expires.
    """
    import psycopg

    class ClientTimeoutError(psycopg.OperationalError):
        """The client closed the connection because `client_timeout` expired."""

    return ClientTimeoutError


def _shut_down_socket(driver_connection):
    """
    Shut the connection's socket down, so that libpq sees EOF and fails at once,
    without psycopg's cancel request to a server that may not answer.
    """
    import psycopg

    try:
        sock = socket.socket(fileno=os.dup(driver_connection.pgconn.socket))
    except (OSError, psycopg.Error):
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    finally:
        sock.close()


async def _guarded(driver_connection, coroutine, timeout):
    """
    Await `coroutine`. If it takes longer than `timeout` seconds, shut the
    connection's socket down and raise `ClientTimeoutError`. The statement may
    keep running on the server.
    """
    fired = False

    def on_timeout():
        nonlocal fired
        fired = True
        callback = driver_connection._crate_on_client_timeout
        if callback is not None:
            callback()
        _shut_down_socket(driver_connection)

    handle = asyncio.get_running_loop().call_later(timeout, on_timeout)
    try:
        return await coroutine
    except Exception as error:
        if fired:
            raise client_timeout_error()(CLIENT_TIMEOUT_MESSAGE.format(timeout)) from error
        raise
    finally:
        handle.cancel()


@functools.lru_cache(maxsize=None)
def _async_connection_class():
    import psycopg

    class CrateAsyncConnection(psycopg.AsyncConnection):
        """
        psycopg runs every network wait of an open connection through `wait()`:
        execute, fetch, pipeline sync, server-side cursors. Hooking it covers them
        all, independent of SQLAlchemy's adapter, whose internals differ between
        SQLAlchemy 2.0 and 2.1. Connecting is bounded by `connect_timeout`.
        """

        _crate_client_timeout: Optional[float] = None
        _crate_on_client_timeout: Optional[Callable[[], None]] = None

        async def wait(self, gen, *args, **kwargs):
            coroutine = super().wait(gen, *args, **kwargs)
            if self._crate_client_timeout:
                coroutine = _guarded(self, coroutine, self._crate_client_timeout)
            return await coroutine

    return CrateAsyncConnection


class HostCooldown:
    """
    Hosts where `client_timeout` expired, left out of new connections for a while.

    Without it, the pool's reconnect after a timeout can pick the frozen host again
    and wait `connect_timeout` on it. A slow statement on a healthy host marks that
    host too; it is only skipped while other hosts remain.
    """

    def __init__(self, seconds: float = HOST_COOLDOWN_SECONDS):
        self.seconds = seconds
        self._until: Dict[Tuple[str, str], float] = {}

    def mark(self, host, port):
        self._until[(str(host), str(port))] = time.monotonic() + self.seconds

    def filter(self, kwargs):
        """
        Drop cooling hosts from libpq's comma-separated `host` and `port` lists.
        Never drops all of them.
        """
        hosts = str(kwargs.get("host") or "").split(",")
        if len(hosts) < 2:
            return kwargs
        ports = str(kwargs.get("port") or "").split(",")
        if len(ports) == 1:
            ports = ports * len(hosts)
        if len(ports) != len(hosts):
            return kwargs
        now = time.monotonic()
        keep = [
            (host, port)
            for host, port in zip(hosts, ports)
            if self._until.get((host, port or "5432"), 0.0) <= now
        ]
        if not keep or len(keep) == len(hosts):
            return kwargs
        return {
            **kwargs,
            "host": ",".join(host for host, _ in keep),
            "port": ",".join(port for _, port in keep),
        }


async def connect(*args, client_timeout, host_cooldown, **kwargs):
    """
    Connect with `client_timeout` applied.
    """
    connection = await _async_connection_class().connect(*args, **host_cooldown.filter(kwargs))
    connection._crate_client_timeout = client_timeout
    connection._crate_on_client_timeout = functools.partial(
        host_cooldown.mark, connection.info.host, connection.info.port
    )
    return connection
