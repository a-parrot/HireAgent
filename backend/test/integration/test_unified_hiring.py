"""Generated PDFs and mocked providers only; exercises real graph and persistence."""

import io
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.main import create_app
from app.models.mysql.entities import Candidate, Reservation, Review
from app.schemas.business import SlotInput
from app.services.resume_service import resumes
from app.services.resume_service.import_runtime import ImportRuntime
from app.services.schedule_service import scheduling
from scripts.seed_job import seed
from test.integration.test_business import batch, config, pdf, runtime

pytestmark = pytest.mark.asyncio


async def test_high_score_skips_review_and_schedules_once(db, tmp_path):
    bid = await batch(db, tmp_path)
    cid = int((await resumes.candidates(db, bid))["items"][0]["id"])
    start = datetime.now(UTC) + timedelta(days=2)
    await scheduling.save_slot(
        db,
        bid,
        SlotInput(
            starts_at=start,
            ends_at=start + timedelta(minutes=45),
            timezone="UTC",
            interviewer="Test",
        ),
    )
    r = await runtime(db, tmp_path)
    try:
        await r.run(cid)
        detail = await resumes.candidate_detail(db, cid)
        assert detail["processing_status"] == "completed"
        assert detail["recommendation"] == "recommended"
        assert detail["review_status"] == "approved"
        assert detail["schedule_status"] == "scheduled"
        assert r.llm.calls == ["Analysis", "Evaluation"]
        assert detail["review_history"][0]["operator_name"] == "系统自动分流"
        await r.run(cid)
        async with db.session() as session:
            assert (
                await session.scalar(select(func.count()).select_from(Reservation)) == 1
            )
            assert await session.scalar(select(func.count()).select_from(Review)) == 1
        assert r.llm.calls == ["Analysis", "Evaluation"]
    finally:
        await r.close()


@pytest.mark.parametrize(
    "ratio,expected", [(0.7, "needs_review"), (0.5, "deferred"), (1, "recommended")]
)
async def test_score_routing_and_no_slots(db, tmp_path, ratio, expected):
    bid = await batch(db, tmp_path)
    cid = int((await resumes.candidates(db, bid))["items"][0]["id"])
    r = await runtime(db, tmp_path)
    generate = r.llm.generate

    async def scaled(prompt, payload, schema):
        result = await generate(prompt, payload, schema)
        if schema.__name__ == "Evaluation":
            for score in result["dimension_scores"]:
                score["score"] *= ratio
        return result

    r.llm.generate = scaled
    try:
        await r.run(cid)
        detail = await resumes.candidate_detail(db, cid)
        assert detail["recommendation"] == expected
        assert (detail["processing_status"] == "waiting_review") == (ratio == 0.7)
        assert ("Verification" in r.llm.calls) == (ratio == 0.7)
        if ratio == 1:
            assert detail["schedule_status"] == "waitlisted"
            assert "尚未配置" in detail["waitlist_reason"]
        else:
            assert detail["schedule_status"] == "unscheduled"
    finally:
        await r.close()


async def test_unified_upload_durable_parse_then_score_duplicate_no_repeat(
    db, tmp_path
):
    jid, _ = await seed(db)
    cfg = config(tmp_path)
    from app.services.job_service.jobs import detail

    version = (await detail(db, int(jid)))["versions"][0]["id"]
    r = await runtime(db, tmp_path)
    imports = ImportRuntime(db, cfg)
    r.imports = imports
    app = create_app(cfg)
    app.state.mysql, app.state.runtime, app.state.import_runtime = db, r, imports
    content = pdf()
    data = {
        "auto_evaluate": "true",
        "rule_version_id": version,
        "request_id": "integration_upload_12345",
    }
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                f"/api/jobs/{jid}/resumes",
                data=data,
                files=[("files", ("test.pdf", io.BytesIO(content), "application/pdf"))],
            )
            assert response.status_code == 201, response.text
            assert response.json()["evaluation"]["status"] == "running"
            tasks = list(r.tasks.values())
            assert len(tasks) == 1
            await tasks[0]
            listing = (await client.get(f"/api/jobs/{jid}/resumes")).json()["items"]
            assert listing[0]["parse_status"] == "completed"
            assert listing[0]["latest_evaluation"]["recommendation"] == "recommended"
            assert listing[0]["latest_evaluation"]["schedule_status"] == "waitlisted"
            again = await client.post(
                f"/api/jobs/{jid}/resumes",
                data=data,
                files=[("files", ("test.pdf", io.BytesIO(content), "application/pdf"))],
            )
            assert again.status_code == 201
            assert again.json()["evaluation"]["already_started"]
            data["request_id"] = "integration_upload_67890"
            duplicate = await client.post(
                f"/api/jobs/{jid}/resumes",
                data=data,
                files=[("files", ("test.pdf", io.BytesIO(content), "application/pdf"))],
            )
            assert duplicate.status_code == 201
            assert "evaluation" not in duplicate.json()
        async with db.session() as session:
            assert (
                await session.scalar(select(func.count()).select_from(Candidate)) == 1
            )
        assert r.llm.calls == [
            "HardConditionScreening",
            "HardConditionScreening",
            "ScoringEvidence",
            "ScoringEvidence",
        ]
    finally:
        await imports.close()
        await r.close()


async def test_parse_failure_stops_scoring_then_retry_uses_local_parser(
    db, tmp_path, monkeypatch
):
    from app.clients.pdf_client import PDFClient
    from app.core.errors import BusinessError
    from app.services.resume_service import workspace
    from app.services.workflow_service import operations
    from test.integration.test_resume_workspace import upload

    jid, _ = await seed(db)
    from app.services.job_service.jobs import detail

    version = (await detail(db, int(jid)))["versions"][0]["id"]
    cfg = config(tmp_path)
    result, _ = await workspace.upload_many(db, cfg, int(jid), [upload()])
    record = await workspace.create_evaluation(
        db,
        int(jid),
        [int(result["items"][0]["resume_id"])],
        int(version),
        config=cfg,
        allow_unparsed=True,
    )
    r = await runtime(db, tmp_path)
    imports = ImportRuntime(db, cfg)
    r.imports = imports
    original_extract = PDFClient.extract
    failed_once = False

    async def fail_once(self, path):
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise BusinessError("本地解析暂时失败", 502)
        return await original_extract(self, path)

    monkeypatch.setattr(PDFClient, "extract", fail_once)
    try:
        await operations.start_batch(db, r, int(record["id"]))
        cid = next(iter(r.tasks))
        await r.tasks[cid]
        failed = await resumes.candidate_detail(db, cid)
        assert failed["processing_status"] == "failed"
        assert failed["error_node"] == "parse_pdf"
        assert r.llm.calls == []
        await operations.retry(db, r, cid)
        await r.tasks[cid]
        assert (await resumes.candidate_detail(db, cid))[
            "recommendation"
        ] == "recommended"
        assert r.llm.calls == [
            "HardConditionScreening",
            "HardConditionScreening",
            "ScoringEvidence",
            "ScoringEvidence",
        ]
    finally:
        await imports.close()
        await r.close()
