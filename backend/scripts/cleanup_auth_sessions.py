"""Manual/cron cleanup of expired or old revoked authentication sessions only."""

import asyncio
from datetime import timedelta

from sqlalchemy import delete, or_

from app.clients.mysql_client import MySQLClient
from app.core.config import Settings
from app.models.mysql.entities import AuthSession, utcnow


async def main():
    db = MySQLClient(Settings())
    try:
        async with db.session() as session:
            now = utcnow()
            result = await session.execute(
                delete(AuthSession).where(
                    or_(
                        AuthSession.expires_at <= now,
                        AuthSession.revoked_at <= now - timedelta(days=7),
                    )
                )
            )
            print(f"Removed expired/revoked sessions: {result.rowcount}")
    finally:
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:  # noqa: BLE001 - avoid printing credentials at CLI boundary
        raise SystemExit("会话清理失败，请检查连接与表结构") from None
