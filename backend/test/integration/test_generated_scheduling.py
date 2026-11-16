from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.models.mysql.entities import (
    Batch,
    Candidate,
    Event,
    File,
    Reservation,
    Review,
    Slot,
)
from app.schemas.business import SlotInput
from app.services.schedule_service import scheduling
from test.integration.test_business import setup_schedule
from test.integration.test_evaluation_actions import application
from test.integration.test_evaluation_management import records

pytestmark = pytest.mark.asyncio


async def test_generate_more_than_four_slots_timezone_and_repeat_idempotency(
    db, tmp_path
):
    bid = await setup_schedule(db, tmp_path)
    async with db.session() as session:
        rows = (
            await session.scalars(select(Candidate).where(Candidate.batch_id == bid))
        ).all()
        for index, candidate in enumerate(rows):
            candidate.total_score = 80 + index
            candidate.recommendation = "recommended"
            candidate.needs_human_review = False
        ordered_ids = [c.id for c in reversed(rows)]
    app = application(db, tmp_path)
    body = {
        "starts_at": "2031-01-01T09:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "interviewer": "面试官 A",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/evaluations/auto-schedule", json=body)
        assert response.status_code == 200, response.text
        assert (
            response.json()["created_slots"] == response.json()["new_reservations"] == 5
        )
        assert response.json()["scheduled"] == 5
        async with db.session() as session:
            appointments = (
                await session.execute(
                    select(Reservation.candidate_id, Slot.starts_at, Slot.ends_at)
                    .join(Slot)
                    .order_by(Slot.starts_at)
                )
            ).all()
            assert [r.candidate_id for r in appointments] == ordered_ids
            for index, item in enumerate(appointments):
                assert item.starts_at == datetime(2031, 1, 1, 1) + timedelta(
                    minutes=45 * index
                )
                assert item.ends_at - item.starts_at == timedelta(minutes=45)
        again = await client.post(
            "/api/evaluations/auto-schedule",
            json={**body, "interviewer": "另一个面试官"},
        )
        assert again.json()["created_slots"] == again.json()["new_reservations"] == 0
    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(Reservation)) == 5
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.event_type == "auto_scheduled")
            )
            == 5
        )
        assigned = (await session.scalars(select(Slot).join(Reservation))).all()
        assert all(s.interviewer == "面试官 A" for s in assigned)


@pytest.mark.parametrize("interviewer,expected_minute", [("A", 45), ("B", 0)])
async def test_generated_slots_skip_same_interviewer_conflicts_across_batches(
    db, tmp_path, interviewer, expected_minute
):
    jid, ids = await records(db)
    start = datetime(2031, 1, 1, 9, tzinfo=UTC)
    async with db.session() as session:
        first = await session.get(Candidate, ids[0])
        bid = first.batch_id
        original_batch = await session.get(Batch, bid)
        other = Batch(
            job_id=jid,
            rule_version_id=original_batch.rule_version_id,
            rule_snapshot=original_batch.rule_snapshot,
            name="Other",
            status="evaluation_done",
        )
        session.add(other)
        await session.flush()
        f = File(
            sha256=uuid4().hex * 2,
            original_name="other.pdf",
            storage_path="test.pdf",
            size_bytes=1,
        )
        session.add(f)
        await session.flush()
        high = Candidate(
            batch_id=other.id,
            file_id=f.id,
            workflow_id=uuid4().hex,
            original_filename="other.pdf",
            total_score=90,
            processing_status="completed",
            recommendation="recommended",
            needs_human_review=False,
        )
        session.add(high)
        await session.flush()
        high_id = high.id
    await scheduling.save_slot(
        db,
        bid,
        SlotInput(
            starts_at=start,
            ends_at=start + timedelta(minutes=45),
            timezone="UTC",
            interviewer="A",
        ),
    )
    await scheduling.schedule(db, bid, automatic=True, candidate_ids=[ids[0]])
    app = application(db, tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/evaluations/auto-schedule",
            json={
                "starts_at": start.isoformat(),
                "timezone": "UTC",
                "interviewer": interviewer,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["new_reservations"] == 1
    async with db.session() as session:
        slot = await session.scalar(
            select(Slot).join(Reservation).where(Reservation.candidate_id == high_id)
        )
        assert slot.starts_at == start.replace(tzinfo=None) + timedelta(
            minutes=expected_minute
        )
        previous = await session.scalar(
            select(Slot).join(Reservation).where(Reservation.candidate_id == ids[0])
        )
        assert previous.starts_at == start.replace(tzinfo=None)


async def test_reuses_exact_available_slot_and_rejects_invalid_start_without_admitting(
    db, tmp_path
):
    _, ids = await records(db)
    async with db.session() as session:
        c = await session.get(Candidate, ids[0])
        bid = c.batch_id
        c.review_status = "pending"
    app = application(db, tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.post(
                "/api/evaluations/auto-schedule",
                json={"starts_at": "2020-01-01T09:00:00Z"},
            )
        ).status_code == 400
        assert (
            await client.post(
                "/api/evaluations/auto-schedule",
                json={"starts_at": "2031-01-01T09:00:00"},
            )
        ).status_code == 422
        assert (
            await client.post(
                "/api/evaluations/auto-schedule",
                json={"starts_at": "2031-01-01T09:00:00Z", "timezone": "invalid-zone"},
            )
        ).status_code == 400
        async with db.session() as session:
            c = await session.get(Candidate, ids[0])
            assert c.review_status == "pending"
            assert await session.scalar(select(func.count()).select_from(Review)) == 0
        start = datetime(2031, 1, 1, 9, tzinfo=UTC)
        await scheduling.save_slot(
            db,
            bid,
            SlotInput(
                starts_at=start,
                ends_at=start + timedelta(minutes=45),
                timezone="UTC",
                interviewer="A",
            ),
        )
        response = await client.post(
            "/api/evaluations/auto-schedule",
            json={
                "starts_at": start.isoformat(),
                "timezone": "UTC",
                "interviewer": "A",
            },
        )
        assert response.status_code == 200, response.text
        assert (
            response.json()["created_slots"] == 0
            and response.json()["new_reservations"] == 1
        )
    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(Slot)) == 1
