import copy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.main import create_app
from app.models.mysql.entities import Batch, Candidate, File, JobRuleVersion, Review
from app.services.resume_service.resumes import candidates
from app.services.review_service.evaluations import list_results
from scripts.seed_job import seed
from test.integration.test_business import batch, config, runtime

pytestmark = pytest.mark.asyncio


async def records(db):
    jid, _ = await seed(db)
    async with db.session() as session:
        version = await session.scalar(select(JobRuleVersion))
        b = Batch(
            job_id=int(jid),
            rule_version_id=version.id,
            rule_snapshot=version.rule_snapshot,
            name="Scores",
            status="evaluation_done",
        )
        session.add(b)
        await session.flush()
        ids = []
        for score in [75, 74.5, 60, 59.99, None, 92]:
            file = File(
                sha256=uuid4().hex * 2,
                original_name=f"resume-{score}.pdf",
                storage_path="test.pdf",
                size_bytes=1,
            )
            session.add(file)
            await session.flush()
            waiting = score in (74.5, 60, 92)
            c = Candidate(
                batch_id=b.id,
                file_id=file.id,
                workflow_id=uuid4().hex,
                original_filename=file.original_name,
                name=f"Candidate {score}",
                total_score=score,
                processing_status="failed"
                if score is None
                else "waiting_review"
                if waiting
                else "completed",
                recommendation=None
                if score is None
                else "needs_review"
                if waiting
                else "recommended"
                if score >= 75
                else "deferred",
                review_status="approved" if score == 75 else "pending",
            )
            session.add(c)
            await session.flush()
            ids.append(c.id)
    return int(jid), ids


async def test_list_returns_latest_final_human_decision_and_reason(db):
    jid, ids = await records(db)
    async with db.session() as session:
        candidate = await session.get(Candidate, ids[1])
        candidate.review_status = "deferred"
        candidate.processing_status = "completed"
        for version, operation, reason in [
            (1, "approve", "初次通过"),
            (2, "defer", "经验待进一步核实"),
            (3, "supplement", "补充说明"),
        ]:
            session.add(
                Review(
                    candidate_id=ids[1],
                    operation=operation,
                    review_version=version,
                    reason=reason,
                    operator_name="审核人员",
                )
            )
    result = await list_results(db, job_id=jid)
    reviewed = next(row for row in result["items"] if row["id"] == str(ids[1]))
    assert reviewed["manual_review"]["operation"] == "defer"
    assert reviewed["manual_review"]["reason"] == "经验待进一步核实"
    assert reviewed["manual_review"]["operator_name"] == "审核人员"
    automatic = next(row for row in result["items"] if row["id"] == str(ids[0]))
    assert automatic["manual_review"] is None


async def test_score_boundaries_and_high_score_still_waits_for_review(db, tmp_path):
    jid, _ = await records(db)
    app = create_app(config(tmp_path))
    app.state.mysql = db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/evaluations", params={"job_id": jid})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["counts"] == {
            "all": 6,
            "high": 2,
            "middle": 2,
            "low": 1,
            "unscored": 1,
        }
        assert body["thresholds"] == [{"recommend": 75, "review": 60}]
        middle = (await client.get("/api/evaluations?bucket=middle")).json()
        assert [r["total_score"] for r in middle["items"]] == [74.5, 60]
        high_review = (
            await client.get("/api/evaluations?bucket=high&workflow=waiting_review")
        ).json()
        assert (
            high_review["total"] == 1 and high_review["items"][0]["total_score"] == 92
        )
        exact = (await client.get("/api/evaluations?min_score=75&max_score=75")).json()
        assert exact["total"] == 1
        assert (await client.get("/api/evaluations?keyword=resume-59")).json()[
            "total"
        ] == 1
        assert (
            await client.get("/api/evaluations?min_score=90&max_score=70")
        ).status_code == 400
        assert (await client.get("/api/evaluations?page_size=2&page=2")).json()[
            "total"
        ] == 6
        assert (await client.get("/api/evaluations?job_id=99999")).json()["total"] == 0


async def test_latest_finished_per_job_file_and_immutable_thresholds(db):
    jid, ids = await records(db)
    async with db.session() as session:
        first = await session.get(Candidate, ids[0])
        version = await session.scalar(select(JobRuleVersion))
        snapshot = copy.deepcopy(version.rule_snapshot)
        snapshot["recommend_threshold"], snapshot["review_threshold"] = 85, 65
        b = Batch(
            job_id=jid,
            rule_version_id=version.id,
            rule_snapshot=snapshot,
            name="New snapshot",
            status="evaluation_done",
        )
        session.add(b)
        await session.flush()
        session.add(
            Candidate(
                batch_id=b.id,
                file_id=first.file_id,
                workflow_id=uuid4().hex,
                original_filename=first.original_filename,
                total_score=80,
                processing_status="waiting_review",
            )
        )
    latest = await list_results(db)
    assert latest["total"] == 6
    assert latest["counts"]["middle"] == 3 and latest["counts"]["high"] == 1
    assert (await list_results(db, latest_only=False))["total"] == 7
    # An in-progress re-evaluation must not hide the last available result.
    async with db.session() as session:
        session.add(
            Candidate(
                batch_id=b.id,
                file_id=(await session.get(Candidate, ids[1])).file_id,
                original_filename="in-progress.pdf",
                workflow_id=uuid4().hex,
                processing_status="running",
            )
        )
    assert (await list_results(db))["total"] == 6


async def test_management_review_and_scheduling_use_real_workflow(db, tmp_path):
    bid = await batch(db, tmp_path)
    cid = int((await candidates(db, bid))["items"][0]["id"])
    r = await runtime(db, tmp_path)
    r.llm.uncertain = True
    app = create_app(config(tmp_path))
    app.state.mysql, app.state.runtime = db, r
    try:
        await r.run(cid)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            pending = (
                await client.get("/api/evaluations?workflow=waiting_review")
            ).json()
            assert pending["total"] == 1
            decision = {
                "operation": "approve",
                "review_version": 0,
                "reason": "核对项目经历",
                "operator_name": "Test reviewer",
            }
            response = await client.post(f"/api/candidates/{cid}/review", json=decision)
            assert response.status_code < 300, response.text
            await r.tasks[cid]
            assert (await client.get("/api/evaluations?workflow=waitlisted")).json()[
                "total"
            ] == 1
            start = datetime(2030, 1, 1, 9, tzinfo=UTC)
            for i in range(4):
                response = await client.post(
                    f"/api/batches/{bid}/slots",
                    json={
                        "starts_at": (start + timedelta(hours=i)).isoformat(),
                        "ends_at": (start + timedelta(hours=i, minutes=45)).isoformat(),
                        "timezone": "UTC",
                    },
                )
                assert response.status_code == 201, response.text
            response = await client.post(f"/api/batches/{bid}/schedule")
            assert response.status_code == 200, response.text
            assert len(response.json()["reservations"]) == 1
            assert (await client.get("/api/evaluations?workflow=scheduled")).json()[
                "total"
            ] == 1
            assert (
                await client.post(f"/api/candidates/{cid}/review", json=decision)
            ).status_code == 409
    finally:
        await r.close()
