"""Upgrade only the slot duration check for databases initialized with SQL."""

import argparse
import asyncio

from sqlalchemy import text

from app.clients.mysql_client import MySQLClient
from app.core.config import Settings


async def main(apply=False):
    client = MySQLClient(Settings())
    try:
        async with client.engine.connect() as connection:
            clause = await connection.scalar(
                text(
                    "SELECT CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS "
                    "WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'ck_slot_duration'"
                )
            )
            print(f"Current duration check: {clause}")
            if apply:
                if not clause:
                    raise RuntimeError(
                        "Missing expected constraint; no changes applied"
                    )
                if (
                    "date_add" in clause.lower()
                    or "interval 45 minute" in clause.lower()
                ):
                    await connection.execute(
                        text(
                            "ALTER TABLE slots DROP CHECK ck_slot_duration, "
                            "ADD CONSTRAINT ck_slot_duration CHECK (ends_at > starts_at)"
                        )
                    )
                    await connection.commit()
                    print("Updated: end must be after start; existing slots preserved")
                else:
                    print("No fixed-duration constraint found; no changes applied")
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
