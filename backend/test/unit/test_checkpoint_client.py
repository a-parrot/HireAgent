from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.clients.checkpoint_client import CheckpointPool, database_error_code


def pool_with(connection):
    @asynccontextmanager
    async def acquire():
        yield connection

    return CheckpointPool(SimpleNamespace(acquire=acquire))


@pytest.mark.asyncio
async def test_health_check_reconnects_before_each_checkpoint_operation():
    connection = SimpleNamespace(ping=AsyncMock(), close=Mock())
    pool = pool_with(connection)
    for _ in range(2):
        async with pool.acquire() as leased:
            assert leased is connection
            assert connection.ping.await_count > 0
    assert connection.ping.await_count == 2
    connection.ping.assert_awaited_with(reconnect=True)
    connection.close.assert_not_called()


@pytest.mark.asyncio
async def test_broken_lease_is_discarded_without_replaying_write():
    connection = SimpleNamespace(ping=AsyncMock(), close=Mock())
    write = Mock(side_effect=RuntimeError("connection lost"))
    with pytest.raises(RuntimeError, match="connection lost"):
        async with pool_with(connection).acquire():
            write()
    write.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.asyncio
async def test_failed_ping_does_not_start_checkpoint_operation():
    connection = SimpleNamespace(ping=AsyncMock(side_effect=OSError()), close=Mock())
    with pytest.raises(OSError):
        async with pool_with(connection).acquire():
            pytest.fail("unhealthy connection was leased")
    connection.close.assert_called_once()


def test_diagnostics_never_include_sql_or_driver_messages():
    error = SimpleNamespace(orig=Exception(2013, "secret SQL and parameters"))
    assert database_error_code(error) == 2013
    assert database_error_code(Exception("secret")) is None
