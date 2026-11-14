"""Async MySQL pool with one transaction/session per operation."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings


class MySQLClient:
    def __init__(self, settings: Settings):
        url = URL.create(
            "mysql+aiomysql",
            username=settings.db_user,
            password=settings.db_password.get_secret_value(),
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            query={"charset": "utf8mb4"},
        )
        self.engine = create_async_engine(
            url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_timeout=10,
            hide_parameters=True,
            connect_args={
                "connect_timeout": settings.db_connect_timeout,
                "init_command": "SET time_zone = '+00:00'",
            },
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.health_timeout = settings.db_connect_timeout + 2

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Commit on success, rollback on error, and always close the session."""
        async with self.session_factory.begin() as session:
            yield session

    async def ping(self) -> None:
        async with asyncio.timeout(self.health_timeout):
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))

    async def close(self) -> None:
        await self.engine.dispose()
