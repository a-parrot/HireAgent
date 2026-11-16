import asyncio
from unittest.mock import AsyncMock

import pytest

from app.clients.mock_external import MockMeetingClient, MockNotificationClient
from app.core.errors import BusinessError
from app.schemas.business import ActionApproval, PreviewInput
from app.services.schedule_service import scheduling
from app.services.schedule_service.actions import ActionService
from test.integration.test_business import setup_schedule

pytestmark = pytest.mark.asyncio


async def prepared(db, tmp_path, meeting, timeout=30):
    bid = await setup_schedule(db, tmp_path)
    rid = int((await scheduling.schedule(db, bid))["reservations"][0]["id"])
    service = ActionService(db, meeting, MockNotificationClient(), timeout=timeout)
    await service.edit_preview(
        rid, PreviewInput(preview_version=0, recipient="demo", content="demo")
    )
    return service, rid


async def test_mock_requires_approval_and_is_idempotent(db, tmp_path):
    service, rid = await prepared(db, tmp_path, MockMeetingClient())
    with pytest.raises(BusinessError):
        await service.execute(rid)
    result = await service.approve(
        rid, ActionApproval(preview_version=1, operator_name="test")
    )
    assert len(result["actions"]) == 2
    assert all(a["provider"] == "mock" for a in result["actions"])
    assert all(a["response_data"]["simulated"] for a in result["actions"])
    again = await service.execute(rid)
    assert all(a["attempt_count"] == 1 for a in again["actions"])


async def test_hanging_provider_times_out_without_resending(db, tmp_path):
    async def hang(*args):
        await asyncio.Event().wait()

    meeting = AsyncMock(configured=True, provider="test")
    meeting.create.side_effect = hang
    service, rid = await prepared(db, tmp_path, meeting, timeout=0.01)
    result = await service.approve(
        rid, ActionApproval(preview_version=1, operator_name="test")
    )
    assert result["actions"][0]["status"] == "uncertain"
    await service.execute(rid)
    assert meeting.create.await_count == 1
