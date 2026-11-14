from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.mysql_client import MySQLClient


def get_mysql_client(request: Request) -> MySQLClient:
    return request.app.state.mysql


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with get_mysql_client(request).session() as session:
        yield session
