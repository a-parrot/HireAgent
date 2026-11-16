import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.main import create_app
from app.models.mysql.entities import Batch, Candidate, Event, File, Reservation
from app.repositories.evaluation_repo.visibility import DELETED_EVENT
from app.schemas.business import SlotInput
from app.services.schedule_service import scheduling
from test.integration.test_business import config
from test.integration.test_evaluation_management import records

pytestmark = pytest.mark.asyncio


def application(db, tmp_path):
    app = create_app(config(tmp_path))
    app.state.mysql = db
    app.state.runtime = SimpleNamespace(db=db, locks={}, ensure_active=lambda: None)
    return app


async def test_delete_invalid_records_preserves_audit_and_blocks_retry_review(
    db, tmp_path
):
    _, ids = await records(db)
    app = application(db, tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/evaluations/delete", json={"candidate_ids": [ids[3], ids[4]]}
        )
        assert response.status_code == 200, response.text
        assert len(response.json()["deleted"]) == 2
        assert (await client.get("/api/evaluations")).json()["total"] == 4
        removed = (await client.get(f"/api/candidates/{ids[4]}")).json()
        assert removed["deleted"]
        assert (await client.post(f"/api/candidates/{ids[4]}/retry")).status_code == 410
        assert (await client.delete(f"/api/evaluations/{ids[4]}")).json()[
            "already_deleted"
        ] == [str(ids[4])]
        assert (await client.delete(f"/api/evaluations/{ids[1]}")).status_code == 200
        assert (
            await client.post(
                f"/api/candidates/{ids[1]}/review",
                json={
                    "operation": "approve",
                    "review_version": 0,
                    "reason": "test",
                    "operator_name": "test",
                },
            )
        ).status_code == 410
        events = (
            await client.get(f"/api/batches/{removed['batch_id']}/events")
        ).json()["items"]
        assert len([e for e in events if e["event_type"] == DELETED_EVENT]) == 3
        assert (await client.get("/api/history/evaluations")).json()["total"] == 1
    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(Candidate)) == 6
        assert await session.scalar(select(func.count()).select_from(File)) == 6


async def test_bulk_delete_is_atomic_and_protects_admitted_or_active_records(
    db, tmp_path
):
    _, ids = await records(db)
    app = application(db, tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.post(
                "/api/evaluations/delete", json={"candidate_ids": [ids[3], ids[0]]}
            )
        ).status_code == 409
        assert (await client.get("/api/evaluations")).json()["total"] == 6
        lock = asyncio.Lock()
        app.state.runtime.locks[ids[4]] = lock
        async with lock:
            assert (
                await client.delete(f"/api/evaluations/{ids[4]}")
            ).status_code == 409
    async with db.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.event_type == DELETED_EVENT)
            )
            == 0
        )


async def test_removed_latest_record_does_not_resurrect_an_older_evaluation(
    db, tmp_path
):
    jid, ids = await records(db)
    async with db.session() as session:
        original = await session.get(Candidate, ids[0])
        old_batch = await session.get(Batch, original.batch_id)
        b = Batch(
            job_id=jid,
            rule_version_id=old_batch.rule_version_id,
            rule_snapshot=old_batch.rule_snapshot,
            name="Retry",
            status="evaluation_done",
        )
        session.add(b)
        await session.flush()
        latest = Candidate(
            batch_id=b.id,
            file_id=original.file_id,
            original_filename=original.original_filename,
            workflow_id=uuid4().hex,
            processing_status="failed",
        )
        session.add(latest)
        await session.flush()
        latest_id = latest.id
    app = application(db, tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.delete(f"/api/evaluations/{latest_id}")).status_code == 200
        data = (await client.get("/api/evaluations")).json()
        assert data["total"] == 5 and all(r["id"] != str(ids[0]) for r in data["items"])
        assert (await client.get("/api/evaluations?latest_only=false")).json()[
            "total"
        ] == 6


async def test_high_score_auto_schedule_waitlist_then_refill_on_slot_creation(
    db, tmp_path
):
    jid, ids = await records(db)
    app = application(db, tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # A 92-point result marked needs_review must never bypass the human decision.
        response = await client.post(
            "/api/evaluations/auto-schedule", json={"job_id": jid}
        )
        assert response.status_code == 200, response.text
        assert response.json()["eligible"] == 1 and response.json()["waitlisted"] == 1
        bid = (await client.get(f"/api/candidates/{ids[0]}")).json()["batch_id"]
        response = await client.post(
            f"/api/batches/{bid}/slots",
            json={
                "starts_at": "2030-01-01T09:00:00Z",
                "ends_at": "2030-01-01T09:45:00Z",
                "timezone": "UTC",
            },
        )
        assert response.status_code == 201, response.text
        assert (await client.get(f"/api/candidates/{ids[0]}")).json()[
            "schedule_status"
        ] == "scheduled"
        response = await client.post(
            "/api/evaluations/auto-schedule", json={"job_id": jid}
        )
        assert response.json()["scheduled"] == 1
        uncertain = (await client.get(f"/api/candidates/{ids[5]}")).json()
        assert (
            uncertain["review_status"] == "pending"
            and uncertain["schedule_status"] == "unscheduled"
        )
        assert (
            await client.post(
                "/api/evaluations/auto-schedule",
                json={"candidate_ids": [ids[5], ids[3], ids[4]]},
            )
        ).json()["eligible"] == 0
        assert (await client.delete(f"/api/evaluations/{ids[0]}")).status_code == 409
    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(Reservation)) == 1


async def test_auto_schedule_only_uses_selected_subset_and_future_slots(db, tmp_path):
    _jid, ids = await records(db)
    async with db.session() as session:
        first = await session.get(Candidate, ids[0])
        bid = first.batch_id
        second = await session.get(Candidate, ids[1])
        second.total_score, second.recommendation, second.processing_status = (
            80,
            "recommended",
            "completed",
        )
        second.needs_human_review = False
    past = datetime(2020, 1, 1, 9, tzinfo=UTC)
    future = datetime(2030, 1, 1, 9, tzinfo=UTC)
    for start in [past, future]:
        await scheduling.save_slot(
            db,
            bid,
            SlotInput(
                starts_at=start, ends_at=start + timedelta(minutes=45), timezone="UTC"
            ),
        )
    app = application(db, tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/evaluations/auto-schedule", json={"candidate_ids": [ids[1]]}
        )
        assert response.status_code == 200, response.text
        assert response.json()["eligible"] == response.json()["scheduled"] == 1
        first = (await client.get(f"/api/candidates/{ids[0]}")).json()
        second = (await client.get(f"/api/candidates/{ids[1]}")).json()
        assert first["schedule_status"] == "unscheduled"
        assert second["reservation"]
        async with db.session() as session:
            from app.models.mysql.entities import Slot

            slot = await session.get(Slot, int(second["reservation"]["slot_id"]))
            assert slot.starts_at.year == 2030


async def test_removed_waiting_record_is_not_recovered_or_run_again(db, tmp_path):
    from unittest.mock import Mock

    from app.models.mysql.entities import utcnow
    from test.integration.test_business import runtime

    _, ids = await records(db)
    r = await runtime(db, tmp_path)
    app = application(db, tmp_path)
    app.state.runtime = r
    try:
        async with db.session() as session:
            record = await session.get(Candidate, ids[1])
            b = await session.get(Batch, record.batch_id)
            b.started_at = utcnow()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (
                await client.delete(f"/api/evaluations/{ids[1]}")
            ).status_code == 200
        r.enqueue = Mock()
        await r.recover()
        r.enqueue.assert_not_called()
        await r.run(ids[1])
        assert r.llm.calls == []
    finally:
        await r.close()


async def test_auto_schedule_uses_snapshot_threshold_instead_of_fixed_75(db, tmp_path):
    _, ids = await records(db)
    async with db.session() as session:
        candidate = await session.get(Candidate, ids[0])
        b = await session.get(Batch, candidate.batch_id)
        b.rule_snapshot = {**b.rule_snapshot, "recommend_threshold": 85}
        candidate.total_score = 80
        candidate.review_status = "pending"  # Threshold still applies before admission.
    app = application(db, tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post("/api/evaluations/auto-schedule", json={})).json()[
            "eligible"
        ] == 0
