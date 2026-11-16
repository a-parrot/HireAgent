"""Reset resume business data, retaining jobs/auth/config and a recoverable backup."""

import argparse
import asyncio
import base64
import json
import shutil
import zipfile
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import MetaData, Table, func, inspect, select, text

from app.clients.mysql_client import MySQLClient
from app.core.config import BACKEND_DIR, Settings

# Child-first order. No foreign-key disabling, truncation, or schema changes.
TABLES = (
    "action_records",
    "reservations",
    "slots",
    "reviews",
    "node_executions",
    "events",
    "candidates",
    "batches",
    "file_pages",
    "file_import_tasks",
    "job_resumes",
    "files",
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoints",
)
KEEP = (
    "jobs",
    "job_rule_versions",
    "auth_users",
    "auth_roles",
    "auth_permissions",
    "auth_sessions",
    "checkpoint_migrations",
)
STORAGE_TARGETS = (
    "uploads",
    "parsed",
    "page_texts",
    "exports",
    "resume-migrations.sql",
)


def encode(value):
    if isinstance(value, bytes):
        return {"__type__": "bytes", "base64": base64.b64encode(value).decode()}
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    raise TypeError(type(value).__name__)


def reflect(connection):
    existing = set(inspect(connection).get_table_names())
    metadata = MetaData()
    return {
        name: Table(name, metadata, autoload_with=connection)
        for name in (*TABLES, *KEEP)
        if name in existing
    }


async def counts(connection, tables):
    return {
        name: await connection.scalar(select(func.count()).select_from(table))
        for name, table in tables.items()
    }


async def main(apply=False):
    config = Settings()
    storage = config.storage_dir.resolve(strict=True)
    workspace = BACKEND_DIR.parent.resolve()
    if not storage.is_relative_to(workspace) or storage in (
        workspace,
        BACKEND_DIR.resolve(),
    ):
        raise RuntimeError(
            "Storage must be a dedicated directory inside this workspace"
        )
    targets = []
    for name in STORAGE_TARGETS:
        target = storage / name
        if target.exists():
            if target.is_symlink() or target.resolve().parent != storage:
                raise RuntimeError("Unexpected storage target; stopped")
            if target.is_dir() and any(p.is_symlink() for p in target.rglob("*")):
                raise RuntimeError("Symlink in storage; stopped")
            targets.append(target)
    db = MySQLClient(config)
    try:
        async with db.engine.connect() as connection:
            tables = await connection.run_sync(reflect)
            before = await counts(connection, tables)
            print(
                json.dumps(
                    {
                        "database": config.db_name,
                        "storage": str(storage),
                        "counts": before,
                        "storage_targets": [p.name for p in targets],
                    },
                    ensure_ascii=True,
                )
            )
            if not apply:
                return
            acquired = await connection.scalar(
                text("SELECT GET_LOCK(:name, 0)"),
                {"name": f"hireagent:{config.db_name}"[:64]},
            )
            if acquired != 1:
                raise RuntimeError("Stop HireAgent backend before resetting data")
            await connection.commit()
            backup_root = storage / "backups"
            if backup_root.is_symlink() or backup_root.resolve().parent != storage:
                raise RuntimeError(
                    "Backup location must stay inside the validated storage directory"
                )
            backup = backup_root / (
                "resume-reset-"
                + datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-%H%M%S-%f")
            )
            backup.mkdir(parents=True, exist_ok=False)
            moved = []
            try:
                async with connection.begin():
                    # Archive DB rows before any destructive SQL; stream to avoid a huge memory copy.
                    with zipfile.ZipFile(
                        backup / "database-rows.zip",
                        "w",
                        compression=zipfile.ZIP_DEFLATED,
                    ) as archive:
                        for name in TABLES:
                            if name not in tables:
                                continue
                            with archive.open(name + ".jsonl", "w") as output:
                                result = await connection.stream(select(tables[name]))
                                async for row in result.mappings():
                                    output.write(
                                        (
                                            json.dumps(
                                                dict(row),
                                                default=encode,
                                                ensure_ascii=True,
                                            )
                                            + "\n"
                                        ).encode()
                                    )
                        archive.writestr(
                            "manifest.json",
                            json.dumps(
                                {
                                    "database": config.db_name,
                                    "counts": before,
                                    "tables": TABLES,
                                    "storage_targets": [p.name for p in targets],
                                },
                                ensure_ascii=True,
                            ),
                        )
                    for target in targets:
                        destination = backup / target.name
                        if (
                            target.resolve().parent != storage
                            or not destination.resolve().is_relative_to(
                                backup.resolve()
                            )
                        ):
                            raise RuntimeError(
                                "Move target escaped validated storage scope"
                            )
                        shutil.move(str(target), str(destination))
                        moved.append((target, destination))
                        if destination.is_dir():
                            target.mkdir()
                    for name in TABLES:
                        if name in tables:
                            await connection.execute(tables[name].delete())
                    remaining = await counts(connection, tables)
                    if any(remaining.get(name, 0) for name in TABLES):
                        raise RuntimeError(
                            "Resume data not fully cleared; rolling back"
                        )
                    if any(
                        remaining.get(name) != before[name]
                        for name in KEEP
                        if name in before
                    ):
                        raise RuntimeError("Retained system data changed; rolling back")
            except BaseException:
                for target, destination in reversed(moved):
                    if target.is_dir():
                        target.rmdir()  # Only remove the empty directory created above.
                    shutil.move(str(destination), str(target))
                raise
            finally:
                await connection.execute(
                    text("SELECT RELEASE_LOCK(:name)"),
                    {"name": f"hireagent:{config.db_name}"[:64]},
                )
                await connection.invalidate()
            print(
                json.dumps(
                    {
                        "cleared": {
                            name: before[name] for name in TABLES if name in before
                        },
                        "backup": str(backup),
                        "remaining": remaining,
                    },
                    ensure_ascii=True,
                )
            )
    finally:
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
