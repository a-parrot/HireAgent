"""Remove the old per-batch start-time restriction without changing appointments."""

import argparse
import asyncio

from sqlalchemy import text

from app.clients.mysql_client import MySQLClient
from app.core.config import Settings


async def main(apply=False):
    client = MySQLClient(Settings())
    try:
        async with client.engine.connect() as connection:
            exists = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'slots' AND INDEX_NAME = 'uk_slot_batch_start'"
                )
            )
            print(f"Old per-batch start-time index present: {bool(exists)}")
            if apply and exists:
                await connection.execute(
                    text("ALTER TABLE slots DROP INDEX uk_slot_batch_start")
                )
                await connection.commit()
                print("Updated; all appointment data preserved")
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
