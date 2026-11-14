from contextlib import asynccontextmanager

import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.mysql.entities import Base


@pytest_asyncio.fixture
async def db(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "business.db"))

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    class Database:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        @asynccontextmanager
        async def session(self):
            async with self.session_factory.begin() as session:
                yield session

    database = Database()
    database.engine = engine
    yield database
    await engine.dispose()
