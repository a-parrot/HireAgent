from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.clients.pdf_client import PDFClient
from app.core.errors import BusinessError
from app.main import create_app
from app.models.mysql.entities import File, FileImportTask, FilePage
from app.services.resume_service import workspace
from app.services.resume_service.import_runtime import ImportRuntime
from app.services.resume_service.resumes import parse_pdf
from scripts.seed_job import seed
from test.integration.test_business import config
from test.integration.test_resume_workspace import upload

pytestmark = pytest.mark.asyncio


async def test_local_pdf_artifacts_full_document_cache_and_content_api(db, tmp_path):
    jid, _ = await seed(db)
    cfg = config(tmp_path)
    result, tasks = await workspace.upload_many(db, cfg, int(jid), [upload()])
    runtime = ImportRuntime(db, cfg)
    try:
        await runtime.run(tasks[0])
    finally:
        await runtime.close()
    file_id = int(result["items"][0]["file_id"])
    sources = await parse_pdf(db, cfg, file_id)
    assert len(sources) == 1 and sources[0]["block_id"] == "document"
    assert sources[0]["page_no"] is None
    async with db.session() as s:
        file = await s.get(File, file_id)
        assert file.parser_name == "pymupdf-text" and file.page_count is None
        assert (
            await s.scalar(select(FilePage.id).where(FilePage.file_id == file_id))
            is None
        )
        assert (cfg.storage_dir / file.markdown_path).is_file()
        task = await s.get(FileImportTask, tasks[0])
        node = next(p for p in task.node_progress if p["name"] == "parse_pdf")
        assert "remote_task" not in node
    app = create_app(cfg)
    app.state.mysql = db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/files/{file_id}/content")
        assert response.status_code == 200
        assert "Managed overseas" in response.json()["markdown"]
        detail = (
            await client.get(
                f"/api/jobs/{jid}/resumes/{result['items'][0]['resume_id']}"
            )
        ).json()
        assert (
            detail["markdown"] == response.json()["markdown"] and detail["pages"] == []
        )


async def test_retry_ignores_old_remote_task_and_extracts_locally(db, tmp_path):
    jid, _ = await seed(db)
    cfg = config(tmp_path)
    result, tasks = await workspace.upload_many(db, cfg, int(jid), [upload()])
    async with db.session() as session:
        task = await session.get(FileImportTask, tasks[0])
        task.node_progress = [
            {
                "name": "parse_pdf",
                "status": "failed",
                "remote_task": {"batch_id": "old", "data_id": "old"},
            }
        ]
    runtime = ImportRuntime(db, cfg)
    try:
        await runtime.run(tasks[0])
    finally:
        await runtime.close()
    detail = await workspace.detail(
        db, cfg, int(jid), int(result["items"][0]["resume_id"])
    )
    assert detail["parse_status"] == "completed" and detail["markdown"]
    assert all(
        "remote_task" not in node for node in detail["import_task"]["node_progress"]
    )


async def test_local_failure_is_persisted(db, tmp_path, monkeypatch):
    jid, _ = await seed(db)
    cfg = config(tmp_path)
    result, tasks = await workspace.upload_many(db, cfg, int(jid), [upload()])
    monkeypatch.setattr(
        PDFClient, "extract", AsyncMock(side_effect=BusinessError("PDF 无法读取"))
    )
    runtime = ImportRuntime(db, cfg)
    try:
        await runtime.run(tasks[0])
    finally:
        await runtime.close()
    detail = await workspace.detail(
        db, cfg, int(jid), int(result["items"][0]["resume_id"])
    )
    assert detail["parse_status"] == "failed" and detail["markdown"] is None
    assert "无法读取" in detail["parse_error"]
