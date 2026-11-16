import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from app.clients.meeting_client import MeetingClient
from app.clients.mock_external import MockMeetingClient, MockNotificationClient
from app.clients.mysql_client import MySQLClient
from app.clients.notification_client import NotificationClient
from app.core.logging import configure_logging
from app.services.resume_service.import_runtime import ImportRuntime
from app.services.schedule_service.actions import ActionService
from app.services.workflow_service.runtime import WorkflowRuntime

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(app.state.settings)
    client = MySQLClient(app.state.settings)
    app.state.mysql = client
    runtime = WorkflowRuntime(client, app.state.settings)
    app.state.runtime = runtime
    mock = app.state.settings.external_services_mock
    app.state.actions = ActionService(
        client,
        MockMeetingClient() if mock else MeetingClient(),
        MockNotificationClient() if mock else NotificationClient(),
        timeout=app.state.settings.external_action_timeout,
    )
    imports = ImportRuntime(client, app.state.settings)
    runtime.imports = imports
    app.state.import_runtime = imports
    runtime.on_lock_lost = imports.suspend
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
        logger.info("MySQL connected; initializing workflow runtime")
        await runtime.start()
        logger.info("Workflow runtime initialized; recovering PDF import tasks")
        await imports.start()
        logger.info("Application ready")
        yield
    finally:
        try:
            await imports.close()
        finally:
            try:
                await runtime.close()
            finally:
                await client.close()
