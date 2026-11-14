from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.clients.notification_client import NotificationClient
from app.models.mysql.entities import ActionRecord, Event
from app.schemas.business import ActionApproval, PreviewInput
from app.services.schedule_service import scheduling
from app.services.schedule_service.actions import ActionService
from test.integration.test_business import setup_schedule

pytestmark = pytest.mark.asyncio


async def service_with_uncertain_meeting(db, tmp_path):
    bid = await setup_schedule(db, tmp_path)
    rid = int((await scheduling.schedule(db, bid))["reservations"][0]["id"])
    meeting = AsyncMock(configured=True, provider="isolation-test")
    meeting.create.side_effect = TimeoutError()
    service = ActionService(db, meeting, NotificationClient())
    await service.edit_preview(
        rid,
        PreviewInput(
            preview_version=0, recipient="test-recipient", content="test-only"
        ),
    )
    await service.approve(
        rid, ActionApproval(preview_version=1, operator_name="tester")
    )
    return service, meeting, rid


async def test_query_failure_keeps_uncertain_and_audits(db, tmp_path):
    service, meeting, rid = await service_with_uncertain_meeting(db, tmp_path)
    meeting.query.side_effect = TimeoutError()
    result = await service.reconcile(rid)
    assert result["actions"][0]["status"] == "uncertain"
    assert meeting.create.await_count == 1
    async with db.session() as session:
        logs = (
            await session.scalars(
                select(Event).where(Event.event_type == "meeting_uncertain")
            )
        ).all()
        assert logs


async def test_confirmed_absence_allows_explicit_retry(db, tmp_path):
    service, meeting, rid = await service_with_uncertain_meeting(db, tmp_path)
    meeting.query.return_value = {"confirmed_absent": True}
    assert (await service.reconcile(rid))["actions"][0]["status"] == "failed"
    assert meeting.create.await_count == 1  # reconciliation itself does not resend
    meeting.create.side_effect = None
    meeting.create.return_value = {"external_id": "test-confirmed-meeting"}
    result = await service.execute(rid)
    assert result["actions"][0]["status"] == "succeeded"
    assert meeting.create.await_count == 2


async def test_confirmed_success_is_not_recreated(db, tmp_path):
    service, meeting, rid = await service_with_uncertain_meeting(db, tmp_path)
    meeting.query.return_value = {
        "external_id": "test-existing-meeting",
        "status": "succeeded",
    }
    result = await service.reconcile(rid)
    assert result["actions"][0]["status"] == "succeeded"
    await service.execute(rid)
    assert meeting.create.await_count == 1
    async with db.session() as session:
        row = await session.scalar(
            select(ActionRecord).where(
                ActionRecord.reservation_id == rid,
                ActionRecord.action_type == "meeting",
            )
        )
        assert row.external_id == "test-existing-meeting"
