"""Reconcile migration records only after validating the installed adapter's final schema."""

import argparse
import asyncio

from langgraph.checkpoint.mysql.base import MIGRATIONS
from sqlalchemy import inspect, text

from app.clients.checkpoint_client import checkpoint_saver
from app.clients.mysql_client import MySQLClient
from app.core.config import Settings


def validate_schema(connection):
    # This repair is intentionally limited to the known 22-migration adapter layout.
    if len(MIGRATIONS) != 22 or "task_path" not in MIGRATIONS[18]:
        raise RuntimeError("Unsupported adapter migration layout; no records changed")
    inspector = inspect(connection)
    keys = {
        "checkpoints": ["thread_id", "checkpoint_ns_hash", "checkpoint_id"],
        "checkpoint_blobs": ["thread_id", "checkpoint_ns_hash", "channel", "version"],
        "checkpoint_writes": [
            "thread_id",
            "checkpoint_ns_hash",
            "checkpoint_id",
            "task_id",
            "idx",
        ],
    }
    for table, expected_key in keys.items():
        columns = {c["name"]: c for c in inspector.get_columns(table)}
        if inspector.get_pk_constraint(table)["constrained_columns"] != expected_key:
            raise RuntimeError(f"{table}: primary key differs; no records changed")
        if (
            columns["checkpoint_ns"]["type"].__class__.__name__ != "VARCHAR"
            or columns["checkpoint_ns"]["type"].length != 2000
        ):
            raise RuntimeError(f"{table}: namespace differs; no records changed")
        hashed = columns.get("checkpoint_ns_hash", {})
        if str(hashed.get("type")).lower() != "binary(16)" or hashed.get("computed"):
            raise RuntimeError(f"{table}: hash column differs; no records changed")
        indexes = {i["name"]: i for i in inspector.get_indexes(table)}
        expected_indexes = {f"{table}_thread_id_idx": ["thread_id"]}
        if table == "checkpoints":
            expected_indexes["checkpoints_checkpoint_id_idx"] = ["checkpoint_id"]
        for name, fields in expected_indexes.items():
            index = indexes.get(name, {})
            if (
                index.get("column_names") != fields
                or index.get("unique")
                or index.get("dialect_options", {}).get("mysql_length")
            ):
                raise RuntimeError(f"{table}: index {name} differs; no records changed")
        if (
            table != "checkpoints"
            and str(columns["blob"]["type"]).lower() != "longblob"
        ):
            raise RuntimeError(f"{table}: blob column differs; no records changed")
        if table == "checkpoint_writes" and (
            columns.get("task_path", {}).get("type").__class__.__name__ != "VARCHAR"
            or getattr(columns.get("task_path", {}).get("type"), "length", None) != 2000
        ):
            raise RuntimeError("task_path differs; no records changed")
        invalid = connection.scalar(
            text(
                f"SELECT COUNT(*) FROM {table} WHERE checkpoint_ns_hash IS NULL "
                "OR checkpoint_ns_hash <> UNHEX(MD5(checkpoint_ns))"
            )
        )
        if invalid:
            raise RuntimeError(f"{table}: invalid namespace hashes; no records changed")


async def main(apply=False):
    config = Settings()
    db = MySQLClient(config)
    try:
        async with db.engine.connect() as connection:
            lock_name = f"hireagent:{config.db_name}"[:64]
            acquired = await connection.scalar(
                text("SELECT GET_LOCK(:name, 0)"), {"name": lock_name}
            )
            if acquired != 1:
                raise RuntimeError("Backend is still running; stop it before repair")
            try:
                await connection.run_sync(validate_schema)
                versions = set(
                    (
                        await connection.scalars(
                            text("SELECT v FROM checkpoint_migrations")
                        )
                    ).all()
                )
                if versions - set(range(len(MIGRATIONS))):
                    raise RuntimeError("Unknown migration versions; no records changed")
                missing = sorted(set(range(len(MIGRATIONS))) - versions)
                print(
                    f"Final schema and namespace hashes verified; missing versions: {missing}"
                )
                if apply and missing:
                    await connection.execute(
                        text("INSERT INTO checkpoint_migrations (v) VALUES (:v)"),
                        [{"v": v} for v in missing],
                    )
                    await connection.commit()
                    print(
                        "Migration records repaired; checkpoint data and indexes preserved"
                    )
            finally:
                await connection.execute(
                    text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name}
                )
                await connection.invalidate()
        if apply:
            async with checkpoint_saver(config) as saver:
                await saver.setup()
            print("Adapter setup completed successfully")
    finally:
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
