"""Initialize only the adapter's tables, without running candidate workflows."""

import asyncio

from langgraph.checkpoint.mysql.aio import AIOMySQLSaver

from app.clients.mysql_client import MySQLClient
from app.core.config import Settings


async def main():
    db = MySQLClient(Settings())
    try:
        async with AIOMySQLSaver.from_conn_string(
            db.engine.url.render_as_string(hide_password=False)
        ) as saver:
            await saver.setup()
        print("MySQL checkpoint tables initialized")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
