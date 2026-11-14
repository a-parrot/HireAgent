import hashlib
import io
import zipfile
from unittest.mock import patch

import httpx
import pytest
from fastapi import UploadFile
from sqlalchemy import func, select

from app.core.errors import BusinessError
from app.main import create_app
from app.models.mysql.entities import File, FileImportTask, JobResume
from app.schemas.business import JobCreate, PublishRequest
from app.services.job_service import jobs
from app.services.resume_service import workspace
from app.services.resume_service.import_runtime import ImportRuntime
from scripts.seed_job import seed
from test.integration.test_business import config, pdf, rules

pytestmark = pytest.mark.asyncio


def upload(data=None, name="resume.pdf"):
    return UploadFile(
        filename=name, file=io.BytesIO(data if data is not None else pdf())
    )


async def ready(db, tmp_path, jid, data=None):
    result, ids = await workspace.upload_many(db, config(tmp_path), jid, [upload(data)])
    runtime = ImportRuntime(db, config(tmp_path))
    for tid in ids:
        await runtime.run(tid)
    return result["items"][0]


async def test_single_multi_hash_partial_rejection_and_cross_job_reuse(db, tmp_path):
    jid, _ = await seed(db)
    jid = int(jid)
    data = pdf()
    digest = hashlib.sha256(data).hexdigest()
    result, tasks = await workspace.upload_many(
        db,
        config(tmp_path),
        jid,
        [
            upload(data),
            upload(data, "renamed.pdf"),
            upload(b"invalid", "bad.txt"),
            upload(data, "mismatch.pdf"),
        ],
        [digest, digest, "", "0" * 64],
    )
    assert (result["accepted"], result["duplicates"], result["rejected"]) == (1, 1, 2)
    assert len(tasks) == 1
    async with db.session() as s:
        assert await s.scalar(select(func.count()).select_from(File)) == 1
        assert await s.scalar(select(func.count()).select_from(JobResume)) == 1
    runtime = ImportRuntime(db, config(tmp_path))
    await runtime.run(tasks[0])
    rid = int(result["items"][0]["resume_id"])
    detail = await workspace.detail(db, config(tmp_path), jid, rid)
    assert detail["sha256_verified"] and detail["parse_status"] == "completed"
    assert "Managed overseas" in detail["pages"][0]["text"]
    assert [n["status"] for n in detail["import_task"]["node_progress"]] == [
        "completed"
    ] * 4
    other = await jobs.create_job(db, JobCreate(name="Other", draft_rules=rules()))
    result2, tasks2 = await workspace.upload_many(
        db, config(tmp_path), int(other["id"]), [upload(data)]
    )
    assert tasks2 == [] and result2["accepted"] == 1
    assert result2["items"][0]["file_id"] == str(detail["file_id"])
    summary = (await workspace.job_summary(db))["items"]
    assert all(j["resume_count"] == 1 and j["parsed_count"] == 1 for j in summary)
    assert (
        await workspace.list_resumes(db, jid, keyword="resume", status="completed")
    )["total"] == 1
    assert (await workspace.list_resumes(db, jid, keyword="missing"))["total"] == 0


async def test_create_from_ready_delete_preserves_history_and_restore(db, tmp_path):
    jid, _ = await seed(db)
    jid = int(jid)
    data = pdf()
    item = await ready(db, tmp_path, jid, data)
    rid = int(item["resume_id"])
    version = (await jobs.detail(db, jid))["versions"][0]
    created = await workspace.create_evaluation(
        db, jid, [rid], int(version["id"]), "new batch"
    )
    assert created["rule_snapshot"] == version["rule_snapshot"]
    assert created["imported_count"] == 1
    await workspace.remove(db, jid, rid)
    assert (await workspace.list_resumes(db, jid))["total"] == 0
    with pytest.raises(BusinessError, match="已移除"):
        await workspace.detail(db, config(tmp_path), jid, rid)
    from app.services.resume_service.resumes import candidates

    assert (await candidates(db, int(created["id"])))["total"] == 1
    with pytest.raises(BusinessError):
        await workspace.create_evaluation(db, jid, [rid], int(version["id"]))
    restored, _ = await workspace.upload_many(db, config(tmp_path), jid, [upload(data)])
    assert restored["items"][0]["resume_id"] == str(rid)
    detail = await workspace.detail(db, config(tmp_path), jid, rid)
    assert len(detail["evaluations"]) == 1
    other = await jobs.create_job(db, JobCreate(name="Other", draft_rules=rules()))
    with pytest.raises(BusinessError):
        await workspace.detail(db, config(tmp_path), int(other["id"]), rid)
    with pytest.raises(BusinessError):
        await workspace.create_evaluation(
            db, int(other["id"]), [rid], int(version["id"])
        )


async def test_original_tampering_stops_parse_and_persists_error(db, tmp_path):
    jid, _ = await seed(db)
    jid = int(jid)
    result, ids = await workspace.upload_many(db, config(tmp_path), jid, [upload()])
    async with db.session() as s:
        file = await s.get(File, int(result["items"][0]["file_id"]))
        (config(tmp_path).storage_dir / file.storage_path).write_bytes(b"tampered")
    await ImportRuntime(db, config(tmp_path)).run(ids[0])
    detail = await workspace.detail(
        db, config(tmp_path), jid, int(result["items"][0]["resume_id"])
    )
    assert detail["parse_status"] == "failed" and not detail["sha256_verified"]
    assert "SHA-256" in detail["parse_error"]
    assert detail["import_task"]["node_progress"][0]["status"] == "failed"


async def test_restart_recovers_pending_and_interrupted_imports(db, tmp_path):
    jid, _ = await seed(db)
    jid = int(jid)
    result, ids = await workspace.upload_many(db, config(tmp_path), jid, [upload()])
    async with db.session() as s:
        task = await s.get(FileImportTask, ids[0])
        task.status = "running"
    runtime = ImportRuntime(db, config(tmp_path))
    await runtime.start()
    await __import__("asyncio").gather(*list(runtime.tasks.values()))
    await runtime.close()
    detail = await workspace.detail(
        db, config(tmp_path), jid, int(result["items"][0]["resume_id"])
    )
    assert detail["parse_status"] == "completed"


async def test_docx_missing_converter_explicit_failure_and_retry(db, tmp_path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("word/document.xml", "<document/>")
    jid, _ = await seed(db)
    jid = int(jid)
    cfg = config(tmp_path)
    cfg.libreoffice_bin = "missing-test-converter"
    result, ids = await workspace.upload_many(
        db, cfg, jid, [upload(stream.getvalue(), "resume.docx")]
    )
    runtime = ImportRuntime(db, cfg)
    await runtime.run(ids[0])
    rid = int(result["items"][0]["resume_id"])
    detail = await workspace.detail(db, cfg, jid, rid)
    assert detail["parse_status"] == "failed" and "LibreOffice" in detail["parse_error"]
    retry = await workspace.retry(db, jid, rid)
    assert retry != ids[0]

    # Test-only converter; no claim of real LibreOffice verification on Windows.
    def convert(cfg, source, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pdf())

    with patch("app.services.resume_service.import_runtime.convert_word", convert):
        await runtime.run(retry)
    detail = await workspace.detail(db, cfg, jid, rid)
    assert detail["parse_status"] == "completed" and detail["pages"][0]["page_no"] == 1


async def test_http_upload_detail_delete_and_unready_evaluation_rejected(db, tmp_path):
    jid, _ = await seed(db)
    jid = int(jid)
    cfg = config(tmp_path)
    app = create_app(cfg)
    app.state.mysql = db
    runtime = ImportRuntime(db, cfg)
    app.state.import_runtime = runtime
    data = pdf()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/jobs/{jid}/resumes",
            files=[("files", ("one.pdf", data, "application/pdf"))],
        )
        assert response.status_code == 201
        rid = response.json()["items"][0]["resume_id"]
        await __import__("asyncio").gather(*list(runtime.tasks.values()))
        assert (await client.get(f"/api/jobs/{jid}/resumes/{rid}")).json()[
            "sha256_verified"
        ]
        assert (await client.get("/api/resume-workspace/jobs")).json()["items"][0][
            "parsed_count"
        ] == 1
        assert (
            await client.get(
                f"/api/files/{response.json()['items'][0]['file_id']}/preview"
            )
        ).status_code == 200
        assert (
            await client.delete(f"/api/jobs/{jid}/resumes/{rid}")
        ).status_code == 204
        assert (await client.get(f"/api/jobs/{jid}/resumes/{rid}")).status_code == 404
    await runtime.close()
    other, ids = await workspace.upload_many(
        db, cfg, jid, [upload(b"%PDF- corrupted", "bad.pdf")]
    )
    version = (await jobs.detail(db, jid))["versions"][0]
    with pytest.raises(BusinessError, match="解析完成"):
        await workspace.create_evaluation(
            db, jid, [int(other["items"][0]["resume_id"])], int(version["id"])
        )
    await ImportRuntime(db, cfg).run(ids[0])
    assert (await workspace.list_resumes(db, jid, status="failed"))["total"] == 1


async def test_completed_original_integrity_checked_before_evaluation_and_reupload_repairs(
    db, tmp_path
):
    jid, _ = await seed(db)
    jid = int(jid)
    data = pdf()
    item = await ready(db, tmp_path, jid, data)
    rid = int(item["resume_id"])
    cfg = config(tmp_path)
    async with db.session() as s:
        file = await s.get(File, int(item["file_id"]))
        (cfg.storage_dir / file.storage_path).write_bytes(b"changed after import")
    version = (await jobs.detail(db, jid))["versions"][0]
    with pytest.raises(BusinessError, match="SHA-256"):
        await workspace.create_evaluation(
            db, jid, [rid], int(version["id"]), config=cfg
        )
    result, ids = await workspace.upload_many(db, cfg, jid, [upload(data)])
    assert result["duplicates"] == 1 and len(ids) == 1
    await ImportRuntime(db, cfg).run(ids[0])
    detail = await workspace.detail(db, cfg, jid, rid)
    assert detail["sha256_verified"] and detail["parse_status"] == "completed"


async def test_unified_evaluation_starts_once_and_shows_latest_result(db, tmp_path):
    from types import SimpleNamespace

    from app.models.mysql.entities import Batch, Candidate

    jid, _ = await seed(db)
    jid = int(jid)
    item = await ready(db, tmp_path, jid)
    version = (await jobs.detail(db, jid))["versions"][0]
    queued = []
    app = create_app(config(tmp_path))
    app.state.mysql = db
    app.state.runtime = SimpleNamespace(enqueue=queued.append, locks={})
    body = {
        "resume_ids": [int(item["resume_id"])],
        "rule_version_id": int(version["id"]),
        "request_id": "evaluation_request_test_001",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(f"/api/jobs/{jid}/evaluate", json=body)
        assert first.status_code == 202 and first.json()["accepted"] == 1
        again = await client.post(f"/api/jobs/{jid}/evaluate", json=body)
        assert again.status_code == 202 and again.json()["already_started"]
        assert len(queued) == 1
        async with db.session() as session:
            assert await session.scalar(select(func.count()).select_from(Batch)) == 1
            candidate = await session.get(Candidate, queued[0])
            candidate.processing_status = "completed"
            candidate.total_score = 88
            candidate.recommendation = "recommended"
        listing = (await client.get(f"/api/jobs/{jid}/resumes")).json()["items"]
        assert listing[0]["latest_evaluation"]["total_score"] == 88
        assert listing[0]["latest_evaluation"]["recommendation"] == "recommended"
        history = (
            await client.get(f"/api/jobs/{jid}/resumes/{item['resume_id']}")
        ).json()["evaluations"]
        assert history[0]["total_score"] == 88 and history[0]["created_at"].endswith(
            "Z"
        )
        async with db.session() as session:
            candidate = await session.get(Candidate, queued[0])
            candidate.processing_status = "failed"
        assert (
            await client.post(f"/api/candidates/{queued[0]}/retry")
        ).status_code == 202
        assert len(queued) == 2
        schema = app.openapi()
        assert "post" not in schema["paths"]["/api/batches"]
        assert "/api/jobs/{job_id}/resume-batches" not in schema["paths"]


async def test_unified_request_reuse_with_changed_rules_rejected(db, tmp_path):
    jid, _ = await seed(db)
    jid = int(jid)
    item = await ready(db, tmp_path, jid)
    version = (await jobs.detail(db, jid))["versions"][0]
    key = "evaluation_request_test_002"
    await workspace.create_evaluation(
        db, jid, [int(item["resume_id"])], int(version["id"]), evaluation_key=key
    )
    draft = await jobs.detail(db, jid)
    newer = await jobs.publish(
        db,
        jid,
        PublishRequest(draft_version=draft["draft_version"], operator_name="test"),
    )
    with pytest.raises(BusinessError, match="同一评估请求"):
        await workspace.create_evaluation(
            db, jid, [int(item["resume_id"])], int(newer["id"]), evaluation_key=key
        )
    other = await jobs.create_job(db, JobCreate(name="Other", draft_rules=rules()))
    assert (await workspace.list_resumes(db, int(other["id"])))["total"] == 0


async def test_individual_export_remains_available_without_batch_pages(db, tmp_path):
    from app.models.mysql.entities import Candidate

    jid, _ = await seed(db)
    jid = int(jid)
    first = await ready(db, tmp_path, jid, pdf())
    second = await ready(db, tmp_path, jid, pdf() + b"\n% distinct test file")
    version = (await jobs.detail(db, jid))["versions"][0]
    record = await workspace.create_evaluation(
        db, jid, [int(first["resume_id"]), int(second["resume_id"])], int(version["id"])
    )
    async with db.session() as session:
        ids = list(
            await session.scalars(
                select(Candidate.id).where(Candidate.batch_id == int(record["id"]))
            )
        )
    assert len(ids) == 2
    app = create_app(config(tmp_path))
    app.state.mysql = db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        result = await client.get(f"/api/candidates/{ids[0]}/export")
        assert result.status_code == 200
        assert [c["id"] for c in result.json()["candidates"]] == [str(ids[0])]
        csv_result = await client.get(f"/api/candidates/{ids[0]}/export?format=csv")
        import csv

        assert (
            len(list(csv.reader(io.StringIO(csv_result.content.decode("utf-8-sig")))))
            == 2
        )
