import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from app.clients.mysql_client import MySQLClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = MySQLClient(app.state.settings)
    app.state.mysql = client
    try:
        try:
            await client.ping()
        except (SQLAlchemyError, OSError, TimeoutError):
            # Do not expose driver exceptions, which may contain connection details.
            logger.error(
                "MySQL startup check failed; verify DB_* configuration and network"
            )
            raise RuntimeError(
                "MySQL unavailable; verify DB_* configuration and network"
            ) from None
        logger.info("MySQL connected; application ready")
        yield
    finally:
        await client.close()
