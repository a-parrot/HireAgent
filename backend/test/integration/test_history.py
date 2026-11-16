from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.clients.pdf_client import PDFClient
from app.main import create_app
from app.models.mysql.entities import File, FileImportTask
from app.services.resume_service import workspace
from app.services.resume_service.import_runtime import ImportRuntime
from scripts.seed_job import seed
from test.integration.test_business import batch, config, runtime
from test.integration.test_resume_workspace import upload

pytestmark = pytest.mark.asyncio


async def test_reparse_keeps_separate_text_snapshots_and_logs(
    db, tmp_path, monkeypatch
):
    jid, _ = await seed(db)
    cfg = config(tmp_path)
    result, tids = await workspace.upload_many(db, cfg, int(jid), [upload()])
    row = result["items"][0]
    monkeypatch.setattr(
        PDFClient,
        "extract",
        AsyncMock(side_effect=["First extracted text", "Second extracted text"]),
    )
    importer = ImportRuntime(db, cfg)
    app = create_app(cfg)
    app.state.mysql = db
    try:
        await importer.run(tids[0])
        second_id = await workspace.retry(db, int(jid), int(row["resume_id"]))
        await importer.run(second_id)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            listing = await client.get(
                "/api/history/imports",
                params={
                    "job_id": jid,
                    "file_id": row["file_id"],
                    "status": "completed",
                    "keyword": "resume",
                },
            )
            assert listing.status_code == 200
            assert listing.json()["total"] == 2
            assert all(r["has_snapshot"] for r in listing.json()["items"])
            first = (await client.get(f"/api/history/imports/{tids[0]}")).json()
            second = (await client.get(f"/api/history/imports/{second_id}")).json()
            assert first["markdown"] == "First extracted text"
            assert second["markdown"] == "Second extracted text"
            assert (
                first["artifact"]["normalized_markdown_path"]
                != second["artifact"]["normalized_markdown_path"]
            )
            assert (await client.get(f"/api/files/{row['file_id']}/content")).json()[
                "markdown"
            ] == "Second extracted text"
            await workspace.remove(db, int(jid), int(row["resume_id"]))
            assert (
                await client.get("/api/history/imports", params={"job_id": jid})
            ).json()["total"] == 2
            assert (await client.get("/api/history/imports/99999")).status_code == 404
            assert (
                await client.get("/api/history/imports?status=unknown")
            ).status_code == 422
            # A missing or modified snapshot must never silently fall back to the current text.
            old_path = cfg.storage_dir / first["artifact"]["normalized_markdown_path"]
            old_path.write_text("changed", encoding="utf-8")
            bad = (await client.get(f"/api/history/imports/{tids[0]}")).json()
            assert bad["markdown"] is None and "校验失败" in bad["artifact_error"]
            old_path.unlink()
            missing = (await client.get(f"/api/history/imports/{tids[0]}")).json()
            assert missing["markdown"] is None and "缺失" in missing["artifact_error"]
    finally:
        await importer.close()


async def test_old_records_do_not_claim_current_text_is_historical(db, tmp_path):
    jid, _ = await seed(db)
    cfg = config(tmp_path)
    _, tids = await workspace.upload_many(db, cfg, int(jid), [upload()])
    async with db.session() as session:
        task = await session.get(FileImportTask, tids[0])
        task.status = "completed"
        task.node_progress = [{"name": "parse_pdf", "status": "completed"}]
        file = await session.get(File, task.file_id)
        file.normalized_markdown_path = "current.md"
    cfg.storage_dir.mkdir(parents=True, exist_ok=True)
    (cfg.storage_dir / "current.md").write_text(
        "Current content only", encoding="utf-8"
    )
    app = create_app(cfg)
    app.state.mysql = db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        record = (await client.get(f"/api/history/imports/{tids[0]}")).json()
        assert record["markdown"] is None and "旧版本" in record["artifact_error"]
        assert not (await client.get("/api/history/imports")).json()["items"][0][
            "has_snapshot"
        ]


async def test_evaluation_history_lists_every_run_and_append_events(db, tmp_path):
    first = await batch(db, tmp_path)
    second = await batch(db, tmp_path)
    from app.models.mysql.entities import Candidate
    from app.services.resume_service.resumes import candidates

    r = await runtime(db, tmp_path)
    try:
        cid = int((await candidates(db, first))["items"][0]["id"])
        await r.run(cid)
        async with db.session() as session:
            failed = await session.scalar(
                select(Candidate).where(Candidate.batch_id == second)
            )
            failed.processing_status = "failed"
        app = create_app(config(tmp_path))
        app.state.mysql = db
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/history/evaluations")
            assert response.status_code == 200
            assert response.json()["total"] == 2
            scheduling = (await client.get("/api/scheduling-records")).json()
            assert scheduling["total"] == 1 and scheduling["items"][0]["id"] == str(
                first
            )
            failures = (
                await client.get("/api/history/evaluations?status=failed")
            ).json()
            assert (
                failures["total"] == 1
                and failures["items"][0]["progress"]["failed"] == 1
            )
            events = (
                await client.get(f"/api/batches/{first}/events?limit=100")
            ).json()["items"]
            assert any(e["node_name"] == "parse_pdf" for e in events)
            assert any(e["event_type"] == "completed" for e in events)
    finally:
        await r.close()


async def test_interview_counts_include_all_reserved_candidates(db, tmp_path):
    from app.services.schedule_service import scheduling
    from test.integration.test_business import setup_schedule

    bid = await setup_schedule(db, tmp_path)
    await scheduling.schedule(db, bid)
    result = await scheduling.list_interview_records(db)
    assert result["total"] == 1
    assert result["items"][0]["interview_count"] == 5
    assert result["items"][0]["scheduled_count"] == 4
