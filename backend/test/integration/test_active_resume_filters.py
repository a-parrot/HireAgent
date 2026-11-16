import pytest
from sqlalchemy import select

from app.models.mysql.entities import Batch, Candidate, NodeExecution
from app.services.resume_service import workspace
from scripts.seed_job import seed
from test.integration.test_business import config, runtime
from test.integration.test_resume_workspace import ready


@pytest.mark.asyncio
async def test_active_filter_runs_before_pagination_and_exposes_fragment_progress(
    db, tmp_path
):
    jid, _ = await seed(db)
    jid = int(jid)
    first = await ready(db, tmp_path, jid)
    await ready(db, tmp_path, jid)
    from app.services.job_service.jobs import detail

    version = (await detail(db, jid))["versions"][0]["id"]
    record = await workspace.create_evaluation(
        db, jid, [int(first["resume_id"])], int(version), config=config(tmp_path)
    )
    async with db.session() as s:
        batch = await s.get(Batch, int(record["id"]))
        from app.models.mysql.entities import utcnow

        batch.started_at = utcnow()
        candidate = await s.scalar(
            select(Candidate).where(Candidate.batch_id == batch.id)
        )
        candidate.processing_status, candidate.current_node = (
            "running",
            "screen_hard_conditions",
        )
        cid = candidate.id
        s.add(
            NodeExecution(
                candidate_id=cid, node_name="screen_hard_conditions", status="running"
            )
        )
    r = await runtime(db, tmp_path)
    try:
        await r.report_progress(cid, "screen_hard_conditions", 2, 4)
        result = await workspace.list_resumes(
            db, jid, page_size=1, evaluation_status="running"
        )
        assert result["total"] == 1 and result["items"][0]["id"] == first["resume_id"]
        assert result["items"][0]["latest_evaluation"]["progress"] == {
            "current": 2,
            "total": 4,
        }
        assert (await workspace.list_resumes(db, jid, evaluation_status="none"))[
            "total"
        ] == 1
        async with db.session() as s:
            c = await s.get(Candidate, cid)
            c.processing_status = "pending"
        assert (await workspace.list_resumes(db, jid, evaluation_status="queued"))[
            "total"
        ] == 1
        assert (await workspace.list_resumes(db, jid, evaluation_status="running"))[
            "total"
        ] == 0
    finally:
        await r.close()
