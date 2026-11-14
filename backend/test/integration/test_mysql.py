"""Explicit opt-in: run against the user's configured MySQL, without changing tables."""

import os

import pytest

from app.clients.mysql_client import MySQLClient
from app.core.config import Settings


@pytest.mark.skipif(os.getenv("RUN_MYSQL_TESTS") != "1", reason="Real MySQL opt-in")
@pytest.mark.asyncio
async def test_mysql_connection():
    database = MySQLClient(Settings())
    try:
        await database.ping()
    finally:
        await database.close()
