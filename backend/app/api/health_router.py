from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import get_mysql_client
from app.clients.mysql_client import MySQLClient

router = APIRouter(prefix="/api/health", tags=["Health"])


@router.get("")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    client: Annotated[MySQLClient, Depends(get_mysql_client)],
) -> dict[str, str]:
    try:
        await client.ping()
    except (SQLAlchemyError, OSError, TimeoutError):
        raise HTTPException(status_code=503, detail="MySQL unavailable") from None
    return {"status": "ready", "database": "ok"}
