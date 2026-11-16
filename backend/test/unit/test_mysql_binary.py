import aiomysql.connection
import pytest

from app.clients.mysql_client import MySQLClient
from app.clients.mysql_compat import ensure_binary_compatibility
from app.core.config import Settings


def test_compatibility_handles_all_binary_values_and_is_idempotent(monkeypatch):
    monkeypatch.setattr(
        aiomysql.connection, "escape_bytes_prefixed", "DO NOT IMPORT THIS!!!"
    )
    assert ensure_binary_compatibility()
    connection = aiomysql.connection.Connection.__new__(aiomysql.connection.Connection)
    connection._writer = None  # No socket is opened by this test.
    payload = bytes(range(256))
    assert connection.escape(payload) == "_binary X'" + payload.hex() + "'"
    assert connection.escape(b"") == "_binary X''"
    assert not ensure_binary_compatibility()


def test_does_not_replace_a_working_driver_alias(monkeypatch):
    def existing(value):
        return "already-supported"

    monkeypatch.setattr(aiomysql.connection, "escape_bytes_prefixed", existing)
    assert not ensure_binary_compatibility()
    assert aiomysql.connection.escape_bytes_prefixed is existing


@pytest.mark.asyncio
async def test_database_constructor_installs_bridge_before_connecting(monkeypatch):
    monkeypatch.setattr(aiomysql.connection, "escape_bytes_prefixed", "removed-alias")
    db = MySQLClient(Settings(_env_file=None))
    try:
        assert callable(aiomysql.connection.escape_bytes_prefixed)
    finally:
        await db.close()
