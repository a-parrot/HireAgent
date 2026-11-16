import copy
import io
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pymupdf
import pytest
from fastapi import UploadFile
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from app.agents.recruitment_agent.recruitment_graph import build_graph
from app.clients.notification_client import NotificationClient
from app.core.config import BACKEND_DIR, Settings
from app.core.errors import BusinessError
from app.main import create_app
from app.models.mysql.entities import (
    Batch,
    Candidate,
    JobRuleVersion,
)
from app.repositories.common import require
from app.schemas.business import (
    ActionApproval,
    JobPatch,
    PreviewInput,
    PublishRequest,
    ReviewRequest,
    SlotInput,
)
from app.services.job_service import jobs
from app.services.resume_service import resumes
from app.services.review_service.reviews import review_candidate
from app.services.schedule_service import scheduling
from app.services.schedule_service.actions import ActionService
from app.services.workflow_service import operations
from app.services.workflow_service.runtime import WorkflowRuntime
from scripts.seed_job import seed

pytestmark = pytest.mark.asyncio


def rules():
    return json.loads(
        (BACKEND_DIR / "app/conf/initial_job.json").read_text(encoding="utf-8")
    )


def config(tmp_path):
    return Settings(
        _env_file=None, storage_dir=tmp_path / "storage", llm_model="test-only"
    )


def pdf():
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "Managed overseas modular projects for 12 years.")
        return doc.tobytes()


async def batch(db, tmp_path, count=1, *, legacy=True):
    job_id, _ = await seed(db)
    async with db.session() as session:
        version = await session.scalar(select(JobRuleVersion))
        version_id = version.id
    content = pdf()
    uploads = [
        UploadFile(filename=f"resume{i}.pdf", file=io.BytesIO(content))
        for i in range(count)
    ]
    result = await resumes.create_batch(
        db, config(tmp_path), int(job_id), version_id, uploads, "Test batch"
    )
    if legacy:
        # Existing regression scenarios represent persisted pre-upgrade workflows.
        # New-flow tests explicitly request legacy=False or use workspace creation.
        async with db.session() as session:
            stored = await session.get(Batch, int(result["id"]))
            snapshot = dict(stored.rule_snapshot)
            snapshot.pop("evaluation_flow", None)
            stored.rule_snapshot = snapshot
    return int(result["id"])


class FakeLLM:
    """Isolation-only test transport, not imported by production code."""

    def __init__(self):
        self.calls = []
        self.uncertain = False

    async def close(self):
        pass

    async def generate(self, prompt, payload, schema):
        self.calls.append(schema.__name__)
        if schema.__name__ == "HardConditionScreening":
            page = payload["pages"][0]
            return {
                "name": "Test Candidate",
                "hard_conditions": [
                    {
                        "condition_id": i,
                        "result": "satisfied",
                        "reason": "documented",
                        "evidence_ids": ["hard_e1"],
                    }
                    for i in jobs.condition_ids(payload["rules"]["hard_conditions"])
                ],
                "evidence": [
                    {
                        "evidence_id": "hard_e1",
                        "file_id": page["file_id"],
                        "block_id": page.get("block_id"),
                        "page_no": page.get("page_no"),
                        "quote": "Managed overseas modular projects for 12 years.",
                    }
                ],
            }
        if schema.__name__ == "ScoringEvidence":
            page = payload["pages"][0]
            eid = payload["chunk_prefix"] + "e1"
            return {
                "name": "Test Candidate",
                "matches": [
                    {
                        "dimension_id": d["id"],
                        "matched": True,
                        "reason": "documented",
                        "evidence_ids": [eid],
                    }
                    for d in payload["rules"]["dimensions"]
                ],
                "evidence": [
                    {
                        "evidence_id": eid,
                        "file_id": page["file_id"],
                        "block_id": page.get("block_id"),
                        "page_no": page.get("page_no"),
                        "quote": "Managed overseas modular projects for 12 years.",
                    }
                ],
            }
        if schema.__name__ == "Analysis":
            page = payload["pages"][0]
            return {
                "name": "Test Candidate",
                "facts": [
                    {
                        "fact_id": "f1",
                        "type": "project",
                        "description": "Managed projects",
                        "evidence_ids": ["e1"],
                    }
                ],
                "evidence": [
                    {
                        "evidence_id": "e1",
                        "file_id": page["file_id"],
                        "page_no": page.get("page_no"),
                        "block_id": page.get("block_id"),
                        "quote": "Managed overseas modular projects for 12 years.",
                    }
                ],
                "missing_fields": [],
            }
        if schema.__name__ == "Evaluation":
            return {
                "hard_conditions": [
                    {
                        "condition_id": i,
                        "result": "satisfied",
                        "reason": "documented",
                        "evidence_ids": ["e1"],
                    }
                    for i in jobs.condition_ids(payload["rules"]["hard_conditions"])
                ],
                "dimension_scores": [
                    {
                        "dimension_id": d["id"],
                        "score": d["max_score"],
                        "reason": "documented",
                        "evidence_ids": ["e1"],
                    }
                    for d in payload["rules"]["dimensions"]
                ],
                "risks": [],
                "missing_fields": ["项目职责待确认"] if self.uncertain else [],
            }
        return {"review_notes": [], "needs_human_review": False}


async def runtime(db, tmp_path, saver=None):
    r = WorkflowRuntime(db, config(tmp_path))
    await r.llm.close()
    r.llm = FakeLLM()
    r.graph = build_graph(r, saver or InMemorySaver())
    return r


async def test_job_versions_and_seed(db):
    job_id, created = await seed(db)
    assert created
    assert await seed(db) == (job_id, False)
    detail = await jobs.detail(db, int(job_id))
    original = copy.deepcopy(detail["versions"][0]["rule_snapshot"])
    await jobs.patch_job(db, int(job_id), JobPatch(draft_version=1, name="New title"))
    with pytest.raises(BusinessError, match="版本"):
        await jobs.publish(
            db, int(job_id), PublishRequest(draft_version=1, operator_name="tester")
        )
    await jobs.publish(
        db, int(job_id), PublishRequest(draft_version=2, operator_name="tester")
    )
    detail = await jobs.detail(db, int(job_id))
    assert detail["versions"][1]["rule_snapshot"] == original
    assert detail["versions"][0]["version_no"] == 2
    await jobs.disable(db, int(job_id))
    assert len((await jobs.detail(db, int(job_id)))["versions"]) == 2


async def test_dynamic_rules():
    value = rules()
    value["dimensions"] = [
        {
            "id": "one",
            "name": "Experience",
            "criteria": "Relevant projects",
            "max_score": 100,
        }
    ]
    value["sort_priority"] = [{"field": "total_score", "direction": "desc"}]
    jobs.validate_rules(value)
    value["dimensions"][0]["max_score"] = 99
    with pytest.raises(BusinessError):
        jobs.validate_rules(value)


async def test_upload_dedup_parse_and_versions(db, tmp_path):
    batch_id = await batch(db, tmp_path, 2)
    result = await resumes.candidates(db, batch_id)
    assert result["total"] == 1
    candidate = result["items"][0]
    pages = await resumes.parse_pdf(db, config(tmp_path), int(candidate["file_id"]))
    assert (
        pages[0]["page_no"] is None
        and pages[0]["block_id"] == "document"
        and "12 years" in pages[0]["text"]
    )
    assert (
        await resumes.parse_pdf(db, config(tmp_path), int(candidate["file_id"]))
        == pages
    )
    with pytest.raises(BusinessError):
        resumes.safe_path(config(tmp_path), "../../private")


async def test_graph_interrupt_restart_and_approval(db, tmp_path):
    batch_id = await batch(db, tmp_path)
    cid = int((await resumes.candidates(db, batch_id))["items"][0]["id"])
    saver = InMemorySaver()
    r = await runtime(db, tmp_path, saver)
    r.llm.uncertain = True
    try:
        await r.run(cid)
        detail = await resumes.candidate_detail(db, cid)
        assert detail["processing_status"] == "waiting_review"
        assert detail["total_score"] == 100
        assert r.llm.calls == ["Analysis", "Evaluation", "Verification"]
        # Simulate shutdown after approval persistence and before background resume.
        r.enqueue = lambda _: None
        await review_candidate(
            db,
            r,
            cid,
            ReviewRequest(
                operation="approve",
                review_version=0,
                reason="verified",
                operator_name="tester",
            ),
        )
        with pytest.raises(BusinessError):
            await review_candidate(
                db,
                r,
                cid,
                ReviewRequest(
                    operation="approve",
                    review_version=0,
                    reason="duplicate",
                    operator_name="tester",
                ),
            )
    finally:
        await r.close()
    restarted = await runtime(db, tmp_path, saver)
    try:
        await restarted.run(cid)
        detail = await resumes.candidate_detail(db, cid)
        assert detail["processing_status"] == "completed"
        assert detail["review_status"] == "approved"
        assert detail["review_history"][0]["resume_status"] == "succeeded"
        assert restarted.llm.calls == []
    finally:
        await restarted.close()


async def test_failed_node_retry_reuses_analysis(db, tmp_path):
    batch_id = await batch(db, tmp_path)
    cid = int((await resumes.candidates(db, batch_id))["items"][0]["id"])
    r = await runtime(db, tmp_path)
    generate = r.llm.generate

    async def failing(prompt, payload, schema):
        if schema.__name__ == "Evaluation":
            raise BusinessError("temporary test failure")
        return await generate(prompt, payload, schema)

    r.llm.generate = failing
    try:
        await r.run(cid)
        assert (await resumes.candidate_detail(db, cid))[
            "processing_status"
        ] == "failed"
        r.llm.generate = generate
        await operations.retry(db, r, cid)
        await r.tasks[cid]
        assert (await resumes.candidate_detail(db, cid))[
            "processing_status"
        ] == "completed"
        assert r.llm.calls.count("Analysis") == 1
    finally:
        await r.close()


async def test_approval_allows_unscored_after_supplement(db, tmp_path):
    batch_id = await batch(db, tmp_path)
    cid = int((await resumes.candidates(db, batch_id))["items"][0]["id"])
    async with db.session() as session:
        c = await require(session, Candidate, cid)
        c.processing_status = "waiting_review"
    r = await runtime(db, tmp_path)
    r.enqueue = lambda candidate_id: None
    try:
        await review_candidate(
            db,
            r,
            cid,
            ReviewRequest(
                operation="supplement",
                review_version=0,
                reason="test",
                operator_name="tester",
                supplements=[{"description": "Clarified", "source": "phone interview"}],
            ),
        )
        detail = await resumes.candidate_detail(db, cid)
        assert detail["review_status"] == "pending"
        await review_candidate(
            db,
            r,
            cid,
            ReviewRequest(
                operation="approve",
                review_version=1,
                operator_name="tester",
            ),
        )
        detail = await resumes.candidate_detail(db, cid)
        assert detail["review_status"] == "approved"
        assert detail["total_score"] is None
    finally:
        await r.close()


async def test_batch_start_is_idempotent(db, tmp_path):
    batch_id = await batch(db, tmp_path)
    r = AsyncMock()
    r.enqueue = __import__("unittest.mock", fromlist=["Mock"]).Mock()
    assert not (await operations.start_batch(db, r, batch_id))["already_started"]
    assert (await operations.start_batch(db, r, batch_id))["already_started"]
    assert r.enqueue.call_count == 1


async def setup_schedule(db, tmp_path):
    batch_id = await batch(db, tmp_path)
    async with db.session() as session:
        b = await require(session, Batch, batch_id)
        b.status = "evaluation_done"
        first = await session.scalar(
            select(Candidate).where(Candidate.batch_id == batch_id)
        )
        # Different candidate files are required by the schema. Add independent indexes.
        from app.models.mysql.entities import File

        for i in range(5):
            if i == 0:
                c = first
            else:
                f = File(
                    sha256=str(i) * 64,
                    original_name="test.pdf",
                    storage_path=f"uploads/{i}.pdf",
                    size_bytes=1,
                )
                session.add(f)
                await session.flush()
                c = Candidate(
                    batch_id=batch_id,
                    file_id=f.id,
                    original_filename="test.pdf",
                    workflow_id=f"schedule-{i}",
                )
                session.add(c)
            c.processing_status, c.review_status, c.total_score = (
                "completed",
                "approved",
                90,
            )
            c.name = f"Candidate {i}"
            c.dimension_scores = [
                {"dimension_id": d["id"], "score": d["max_score"]}
                for d in rules()["dimensions"]
            ]
    start = datetime(2030, 1, 1, 9, tzinfo=UTC)
    for i in range(4):
        await scheduling.save_slot(
            db,
            batch_id,
            SlotInput(
                starts_at=start + timedelta(hours=i),
                ends_at=start + timedelta(hours=i, minutes=45),
            ),
        )
    return batch_id


async def test_scheduling_ties_capacity_and_repetition(db, tmp_path):
    batch_id = await setup_schedule(db, tmp_path)
    result = await scheduling.schedule(db, batch_id)
    assert len(result["reservations"]) == 4 and len(result["waitlist"]) == 1
    assert result == await scheduling.schedule(db, batch_id)
    assert [int(r["candidate_id"]) for r in result["reservations"]] == sorted(
        int(r["candidate_id"]) for r in result["reservations"]
    )
    with pytest.raises(BusinessError):
        await scheduling.delete_slot(db, int(result["reservations"][0]["slot_id"]))


async def test_actions_authorization_and_notification_only_retry(db, tmp_path):
    batch_id = await setup_schedule(db, tmp_path)
    reservation_id = int(
        (await scheduling.schedule(db, batch_id))["reservations"][0]["id"]
    )
    meeting = AsyncMock(configured=True, provider="test")
    meeting.create.return_value = {
        "external_id": "test-meeting",
        "meeting_url": "https://example.invalid/join",
    }
    notification = AsyncMock(configured=True, provider="test")
    notification.send.side_effect = BusinessError("test delivery failed")
    service = ActionService(db, meeting, notification)
    with pytest.raises(BusinessError):
        await service.execute(reservation_id)
    await service.edit_preview(
        reservation_id,
        PreviewInput(
            preview_version=0, recipient="test-recipient", content="Test notification"
        ),
    )
    result = await service.approve(
        reservation_id, ActionApproval(preview_version=1, operator_name="tester")
    )
    assert [a["status"] for a in result["actions"]] == ["succeeded", "failed"]
    notification.send.side_effect = None
    notification.send.return_value = {"external_id": "test-notification"}
    await service.execute(reservation_id)
    await service.execute(reservation_id)
    assert meeting.create.await_count == 1 and notification.send.await_count == 2


async def test_uncertain_actions_never_blindly_repeat(db, tmp_path):
    batch_id = await setup_schedule(db, tmp_path)
    rid = int((await scheduling.schedule(db, batch_id))["reservations"][0]["id"])
    meeting = AsyncMock(configured=True, provider="test")
    meeting.create.side_effect = TimeoutError()
    service = ActionService(db, meeting, NotificationClient())
    await service.edit_preview(
        rid, PreviewInput(preview_version=0, recipient="test", content="test")
    )
    await service.approve(
        rid, ActionApproval(preview_version=1, operator_name="tester")
    )
    result = await service.execute(rid)
    assert result["actions"][0]["status"] == "uncertain"
    assert meeting.create.await_count == 1


async def test_export_and_http_errors(db, tmp_path):
    batch_id = await batch(db, tmp_path)
    raw, _ = await operations.export(db, batch_id, "json")
    assert json.loads(raw)["batch"]["id"] == str(batch_id)
    csv, _ = await operations.export(db, batch_id, "csv")
    assert csv.startswith(b"\xef\xbb\xbf")
    assert operations.csv_safe("=1+1").startswith("'")
    app = create_app(config(tmp_path))
    app.state.mysql = db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/jobs/99999")).status_code == 404
        assert (
            await client.post("/api/jobs", json={"name": "Backend test"})
        ).status_code == 201
        assert (await client.get(f"/api/batches/{batch_id}")).json()["total"] == 1
