from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from app.models.mysql.entities import Batch, Candidate, Review, utcnow
from app.repositories.common import require
from app.schemas.business import ReviewRequest
from app.services.resume_service.resumes import candidate_detail, candidates
from app.services.review_service.reviews import review_candidate
from test.integration.test_business import batch, runtime

pytestmark = pytest.mark.asyncio


async def test_recovery_repairs_batch_after_last_candidate_committed(db, tmp_path):
    bid = await batch(db, tmp_path)
    async with db.session() as session:
        candidate = await session.scalar(
            select(Candidate).where(Candidate.batch_id == bid)
        )
        candidate.processing_status = "waiting_review"
        b = await require(session, Batch, bid)
        b.started_at = utcnow()
        b.status = "running"
    r = await runtime(db, tmp_path)
    r.enqueue = Mock()
    try:
        await r.recover()
        async with db.session() as session:
            b = await require(session, Batch, bid)
            assert b.status == "evaluation_done"
            assert b.evaluation_completed_at is not None
        r.enqueue.assert_not_called()
    finally:
        await r.close()


async def test_recovery_reschedules_pending_in_started_batch(db, tmp_path):
    bid = await batch(db, tmp_path)
    cid = int((await candidates(db, bid))["items"][0]["id"])
    async with db.session() as session:
        b = await require(session, Batch, bid)
        b.started_at = utcnow()
    r = await runtime(db, tmp_path)
    r.enqueue = Mock()
    try:
        await r.recover()
        r.enqueue.assert_called_once_with(cid)
    finally:
        await r.close()


async def test_recovery_after_graph_finished_before_business_status_commit(
    db, tmp_path
):
    bid = await batch(db, tmp_path)
    cid = int((await candidates(db, bid))["items"][0]["id"])
    r = await runtime(db, tmp_path)
    try:
        await r.run(cid)
        await review_candidate(
            db,
            r,
            cid,
            ReviewRequest(
                operation="approve",
                review_version=0,
                reason="test",
                operator_name="tester",
            ),
        )
        await r.tasks[cid]
        assert (await candidate_detail(db, cid))["processing_status"] == "completed"
        async with db.session() as session:
            c = await require(session, Candidate, cid)
            c.processing_status = "waiting_review"
            row = await session.scalar(select(Review).where(Review.candidate_id == cid))
            row.resume_status = "pending"
        await r.run(cid)
        detail = await candidate_detail(db, cid)
        assert detail["processing_status"] == "completed"
        assert detail["review_history"][0]["resume_status"] == "succeeded"
        assert r.llm.calls == ["Analysis", "Evaluation", "Verification"]
    finally:
        await r.close()


async def test_shutdown_releases_contexts_when_unlock_fails(db, tmp_path):
    r = await runtime(db, tmp_path)
    r.runtime_connection = AsyncMock()
    r.runtime_connection.execute.side_effect = RuntimeError("simulated disconnect")
    r.lock_name = "test"
    r.stack = AsyncMock()
    with pytest.raises(RuntimeError, match="simulated disconnect"):
        await r.close()
    r.stack.aclose.assert_awaited_once()
