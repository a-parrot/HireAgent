import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from app.clients.meeting_client import MeetingClient
from app.clients.mysql_client import MySQLClient
from app.clients.notification_client import NotificationClient
from app.services.resume_service.import_runtime import ImportRuntime
from app.services.schedule_service.actions import ActionService
from app.services.workflow_service.runtime import WorkflowRuntime

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = MySQLClient(app.state.settings)
    app.state.mysql = client
    runtime = WorkflowRuntime(client, app.state.settings)
    app.state.runtime = runtime
    app.state.actions = ActionService(client, MeetingClient(), NotificationClient())
    imports = ImportRuntime(client, app.state.settings)
    app.state.import_runtime = imports
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
        await runtime.start()
        await imports.start()
        yield
    finally:
        try:
            await imports.close()
        finally:
            try:
                await runtime.close()
            finally:
                await client.close()
