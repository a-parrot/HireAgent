import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from app.core.errors import BusinessError
from app.models.mysql.entities import Candidate, Event, NodeExecution
from app.services.resume_service.resumes import candidate_detail, candidates
from app.services.workflow_service import operations
from test.integration.test_business import batch, runtime

pytestmark = pytest.mark.asyncio


async def prepare_failed_review(db, tmp_path):
    bid = await batch(db, tmp_path)
    cid = int((await candidates(db, bid))["items"][0]["id"])
    saver = InMemorySaver()
    r = await runtime(db, tmp_path, saver)
    r.llm.uncertain = True
    await r.run(cid)
    assert (await candidate_detail(db, cid))["processing_status"] == "waiting_review"
    async with db.session() as session:
        c = await session.get(Candidate, cid)
        workflow_id = c.workflow_id
        c.processing_status, c.error_node, c.error_message = (
            "failed",
            "human_review",
            "checkpoint failed",
        )
    await saver.adelete_thread(workflow_id)
    return r, cid


async def test_review_recovery_reuses_saved_nodes_when_checkpoint_was_lost(
    db, tmp_path
):
    r, cid = await prepare_failed_review(db, tmp_path)
    try:

        async def reject_model(*args, **kwargs):
            raise AssertionError("cached recovery must never call a model")

        r.llm.generate = reject_model
        await operations.retry(db, r, cid, cached_review_only=True)
        await r.tasks[cid]
        detail = await candidate_detail(db, cid)
        assert detail["processing_status"] == "waiting_review"
        assert detail["error_message"] is None and detail["review_status"] == "pending"
        assert r.llm.calls == ["Analysis", "Evaluation", "Verification"]
        async with db.session() as session:
            assert await session.scalar(
                select(Event.id).where(
                    Event.candidate_id == cid,
                    Event.event_type == "review_recovery_requested",
                )
            )
    finally:
        await r.close()


@pytest.mark.parametrize("missing_output", [None, {}])
async def test_cached_recovery_rejects_incomplete_outputs_without_model_request(
    db, tmp_path, missing_output
):
    r, cid = await prepare_failed_review(db, tmp_path)
    try:
        async with db.session() as session:
            row = await session.scalar(
                select(NodeExecution).where(
                    NodeExecution.candidate_id == cid,
                    NodeExecution.node_name == "analyze_resume",
                )
            )
            row.output_data = missing_output
        with pytest.raises(BusinessError, match="缺少完整"):
            await operations.retry(db, r, cid, cached_review_only=True)
        assert (await candidate_detail(db, cid))["processing_status"] == "failed"
        assert cid not in r.tasks
    finally:
        await r.close()
