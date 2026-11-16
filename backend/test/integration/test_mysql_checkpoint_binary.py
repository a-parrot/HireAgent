"""Opt-in synthetic-only MySQL checkpoint check; no business records or DDL."""

import os

import pytest

from app.core.config import Settings
from scripts.verify_checkpoint_recovery import verify


@pytest.mark.skipif(
    os.getenv("RUN_MYSQL_CHECKPOINT_TESTS") != "1",
    reason="Real MySQL synthetic checkpoint opt-in",
)
@pytest.mark.asyncio
async def test_mysql_binary_interrupt_and_reconnect():
    result = await verify(Settings())
    assert all(result.values()) and len(result) == 4
