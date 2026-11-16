import asyncio
from datetime import datetime

import httpx
import pytest
from app.models.mysql.entities import Batch, Candidate, Reservation, Review, Slot
from sqlalchemy import func, select
from test.integration.test_business import setup_schedule
from test.integration.test_evaluation_actions import application


@pytest.mark.asyncio
@pytest.mark.parametrize("generate", [True, False])
async def test_manual_approval_overrides_score_threshold_and_batch_wait(
    db, tmp_path, generate
):
    bid = await setup_schedule(db, tmp_path)
    async with db.session() as s:
        batch = await s.get(Batch, bid)
        batch.status = "running"
        batch.rule_snapshot = {
            **batch.rule_snapshot,
            "sort_priority": [
                {"field": "total_score", "direction": "desc"},
                {"field": "management", "direction": "desc"},
            ],
        }
        rows = (
            await s.scalars(
                select(Candidate)
                .where(Candidate.batch_id == bid)
                .order_by(Candidate.id)
            )
        ).all()
        for index, score in enumerate([60, None, 60, 99, 80]):
            rows[index].total_score = score
            rows[index].recommendation = "needs_review"
            rows[index].needs_human_review = True
            rows[index].dimension_scores = [
                {"dimension_id": "management", "score": index * 5}
            ]
        rows[
            0
        ].processing_status = (
            "waiting_review"  # Approval already saved; worker still queued.
        )
        rows[
            1
        ].recommendation = (
            "deferred"  # A low original AI score does not undo manual approval.
        )
        rows[1].processing_status = "failed"
        rows[3].review_status, rows[3].processing_status = "pending", "running"
        rows[4].review_status = "deferred"
        expected = [rows[2].id, rows[0].id, rows[1].id]
        rejected = [rows[3].id, rows[4].id]
    app = application(db, tmp_path)
    # A human-resume task can be waiting behind model work while retaining this lock.
    held = asyncio.Lock()
    await held.acquire()
    app.state.runtime.locks[expected[1]] = held
    body = (
        {"starts_at": "2032-01-01T09:00:00+08:00", "timezone": "Asia/Shanghai"}
        if generate
        else {}
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await asyncio.wait_for(
            client.post("/api/evaluations/auto-schedule", json=body), 5
        )
        held.release()
        assert response.status_code == 200, response.text
        assert response.json()["eligible"] == response.json()["scheduled"] == 3
        again = await client.post("/api/evaluations/auto-schedule", json=body)
        assert again.status_code == 200
    async with db.session() as s:
        appointments = (
            await s.execute(
                select(Reservation.candidate_id, Slot.starts_at)
                .join(Slot)
                .order_by(Slot.starts_at)
            )
        ).all()
        assert [r.candidate_id for r in appointments] == expected
        assert not set(rejected) & {r.candidate_id for r in appointments}
        assert await s.scalar(select(func.count()).select_from(Review)) == 0
        assert (await s.get(Batch, bid)).status == "running"
        if generate:
            assert appointments[0].starts_at == datetime(2032, 1, 1, 1)
