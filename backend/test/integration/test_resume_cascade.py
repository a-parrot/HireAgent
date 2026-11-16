import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.core.errors import BusinessError
from app.models.mysql.entities import (
    ActionRecord,
    Batch,
    Candidate,
    Event,
    File,
    Reservation,
    Slot,
)
from app.repositories.evaluation_repo.visibility import is_deleted
from app.schemas.business import JobCreate, PublishRequest
from app.services.job_service import jobs
from app.services.resume_service import workspace
from app.services.review_service.evaluations import list_results
from app.services.schedule_service.interviews import list_interviews
from scripts.seed_job import seed
from test.integration.test_business import config, rules
from test.integration.test_resume_workspace import ready, upload

pytestmark = pytest.mark.asyncio


async def test_cascade_is_scoped_to_current_job_for_shared_original(db, tmp_path):
    jid, rid, _, _ = await setup_records(db, tmp_path)
    other = await jobs.create_job(db, JobCreate(name="Other job", draft_rules=rules()))
    other_id = int(other["id"])
    await jobs.publish(
        db, other_id, PublishRequest(draft_version=1, operator_name="test")
    )
    async with db.session() as session:
        original = await session.scalar(select(File))
        shared_bytes = (
            config(tmp_path).storage_dir / original.storage_path
        ).read_bytes()
    imported, _ = await workspace.upload_many(
        db, config(tmp_path), other_id, [upload(shared_bytes)]
    )
    other_rid = int(imported["items"][0]["resume_id"])
    version = int((await jobs.detail(db, other_id))["versions"][0]["id"])
    batch = await workspace.create_evaluation(db, other_id, [other_rid], version)
    async with db.session() as session:
        candidate = await session.scalar(
            select(Candidate).where(Candidate.batch_id == int(batch["id"]))
        )
        candidate.processing_status, candidate.review_status, candidate.total_score = (
            "completed",
            "approved",
            80,
        )
        other_cid = candidate.id
    await workspace.remove(db, jid, rid)
    assert (await workspace.list_resumes(db, other_id))["total"] == 1
    assert (await list_results(db, job_id=other_id))["total"] == 1
    assert (await list_interviews(db))["total"] == 1
    async with db.session() as session:
        assert not await is_deleted(session, other_cid)


async def setup_records(db, tmp_path):
    jid, _ = await seed(db)
    jid = int(jid)
    item = await ready(db, tmp_path, jid)
    rid = int(item["resume_id"])
    version = int((await jobs.detail(db, jid))["versions"][0]["id"])
    batches = [
        await workspace.create_evaluation(db, jid, [rid], version) for _ in range(2)
    ]
    async with db.session() as session:
        candidates = (
            await session.scalars(select(Candidate).order_by(Candidate.id))
        ).all()
        ids = [c.id for c in candidates]
        for candidate in candidates:
            candidate.processing_status, candidate.review_status = (
                "completed",
                "approved",
            )
            candidate.total_score, candidate.schedule_status = 80, "scheduled"
            slot = Slot(
                batch_id=candidate.batch_id,
                starts_at=datetime(2032, 1, candidate.id, 1),
                ends_at=datetime(2032, 1, candidate.id, 2),
                timezone="Asia/Shanghai",
            )
            session.add(slot)
            await session.flush()
            session.add(
                Reservation(
                    batch_id=candidate.batch_id,
                    candidate_id=candidate.id,
                    slot_id=slot.id,
                    priority_snapshot={},
                )
            )
    return jid, rid, ids, batches


async def test_resume_delete_cascades_all_evaluations_and_interviews_atomically(
    db, tmp_path
):
    jid, rid, ids, batches = await setup_records(db, tmp_path)
    await workspace.remove(db, jid, rid, SimpleNamespace(locks={}))
    assert (await workspace.list_resumes(db, jid))["total"] == 0
    assert (await list_results(db, job_id=jid, latest_only=False))["total"] == 0
    assert (await list_interviews(db))["total"] == 0
    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(Reservation)) == 0
        assert await session.scalar(select(func.count()).select_from(Slot)) == 0
        assert await session.scalar(select(func.count()).select_from(File)) == 1
        for cid in ids:
            assert await is_deleted(session, cid)
        for batch in batches:
            assert (
                await session.get(Batch, int(batch["id"]))
            ).status == "evaluation_done"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.event_type == "interview_cancelled")
            )
            == 2
        )


async def test_external_action_blocks_entire_cascade_without_partial_removal(
    db, tmp_path
):
    jid, rid, ids, _ = await setup_records(db, tmp_path)
    async with db.session() as session:
        reservation = await session.scalar(
            select(Reservation).where(Reservation.candidate_id == ids[-1])
        )
        session.add(
            ActionRecord(
                reservation_id=reservation.id,
                action_type="meeting",
                idempotency_key="cascade-test",
                status="succeeded",
                attempt_count=1,
            )
        )
    with pytest.raises(BusinessError, match="会议或通知"):
        await workspace.remove(db, jid, rid)
    assert (await workspace.list_resumes(db, jid))["total"] == 1
    assert (await list_interviews(db))["total"] == 2
    async with db.session() as session:
        assert not any([await is_deleted(session, cid) for cid in ids])
        assert await session.scalar(select(func.count()).select_from(Slot)) == 2


async def test_running_workflow_blocks_cascade(db, tmp_path):
    jid, rid, ids, _ = await setup_records(db, tmp_path)
    lock = asyncio.Lock()
    async with lock:
        with pytest.raises(BusinessError, match="处理中"):
            await workspace.remove(db, jid, rid, SimpleNamespace(locks={ids[0]: lock}))
    assert (await workspace.list_resumes(db, jid))["total"] == 1
