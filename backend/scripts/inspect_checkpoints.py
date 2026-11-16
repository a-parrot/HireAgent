"""Read-only checkpoint migration and index diagnostics."""

import asyncio
import json

from sqlalchemy import text

from app.clients.mysql_client import MySQLClient
from app.core.config import Settings


async def main():
    db = MySQLClient(Settings())
    try:
        async with db.engine.connect() as connection:
            versions = (
                await connection.scalars(
                    text("SELECT v FROM checkpoint_migrations ORDER BY v")
                )
            ).all()
            indexes = (
                (
                    await connection.execute(
                        text(
                            "SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME,SUB_PART "
                            "FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() "
                            "AND TABLE_NAME IN ('checkpoints','checkpoint_blobs','checkpoint_writes') "
                            "AND INDEX_NAME LIKE '%thread_id_idx' ORDER BY TABLE_NAME,SEQ_IN_INDEX"
                        )
                    )
                )
                .mappings()
                .all()
            )
            columns = (
                (
                    await connection.execute(
                        text(
                            "SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,EXTRA,GENERATION_EXPRESSION FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('checkpoints','checkpoint_blobs','checkpoint_writes')"
                        )
                    )
                )
                .mappings()
                .all()
            )
            keys = (
                (
                    await connection.execute(
                        text(
                            "SELECT TABLE_NAME,INDEX_NAME,COLUMN_NAME,SEQ_IN_INDEX FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('checkpoints','checkpoint_blobs','checkpoint_writes') ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX"
                        )
                    )
                )
                .mappings()
                .all()
            )
            print(
                json.dumps(
                    {
                        "migration_versions": versions,
                        "indexes": [dict(row) for row in indexes],
                        "columns": [dict(row) for row in columns],
                        "all_indexes": [dict(row) for row in keys],
                    }
                )
            )
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
