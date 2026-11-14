import asyncio

from alembic import context
from app.clients.mysql_client import MySQLClient
from app.core.config import Settings
from app.models.mysql.entities import Base


def run_migrations(connection):
    context.configure(
        connection=connection, target_metadata=Base.metadata, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


async def online():
    client = MySQLClient(Settings())
    try:
        async with client.engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await client.close()


if context.is_offline_mode():
    context.configure(
        dialect_name="mysql", target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
