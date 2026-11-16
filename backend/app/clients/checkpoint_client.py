"""Short-lived, health-checked leases for LangGraph checkpoint operations."""

from contextlib import asynccontextmanager

import aiomysql
from langgraph.checkpoint.mysql.aio import AIOMySQLSaver


class CheckpointPool:
    def __init__(self, pool):
        self.pool = pool

    @asynccontextmanager
    async def acquire(self):
        async with self.pool.acquire() as connection:
            try:
                # Reconnect only before an operation; never replay checkpoint writes.
                await connection.ping(reconnect=True)
                yield connection
            except BaseException:
                # Discard a broken or cancelled lease, including open transactions.
                connection.close()
                raise


@asynccontextmanager
async def checkpoint_saver(settings):
    pool = await aiomysql.create_pool(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password.get_secret_value(),
        db=settings.db_name,
        charset="utf8mb4",
        autocommit=True,
        minsize=1,
        maxsize=settings.db_pool_size,
        pool_recycle=1800,
        connect_timeout=settings.db_connect_timeout,
        init_command="SET time_zone = '+00:00'",
    )
    try:
        yield AIOMySQLSaver(CheckpointPool(pool))
    finally:
        pool.close()
        await pool.wait_closed()


def database_error_code(exc):
    """Return only the numeric driver code, never SQL, parameters or payloads."""
    original = getattr(exc, "orig", exc)
    args = getattr(original, "args", ())
    return args[0] if args and type(args[0]) is int else None
