import io

import httpx
import pytest
from fastapi import UploadFile

from app.core.errors import BusinessError
from app.main import create_app
from app.models.mysql.entities import Job, JobRuleVersion
from app.schemas.business import JobPatch
from app.services.job_service import jobs
from app.services.resume_service import resumes
from test.integration.test_business import batch, config, pdf

pytestmark = pytest.mark.asyncio


async def test_deleted_job_hidden_but_history_preserved(db, tmp_path):
    bid = await batch(db, tmp_path)
    before = await resumes.batch_detail(db, bid)
    jid = int(before["job_id"])
    detail = await jobs.detail(db, jid)
    version = detail["versions"][0]
    await jobs.delete_job(db, jid)
    assert (await jobs.list_jobs(db, 1, 50))["total"] == 0
    with pytest.raises(BusinessError, match="已删除"):
        await jobs.detail(db, jid)
    assert (await resumes.batch_detail(db, bid))["rule_snapshot"] == before[
        "rule_snapshot"
    ]
    async with db.session() as session:
        job = await session.get(Job, jid)
        assert job.deleted_at is not None
        assert await session.get(JobRuleVersion, int(version["id"])) is not None
    with pytest.raises(BusinessError):
        await resumes.create_batch(
            db,
            config(tmp_path),
            jid,
            int(version["id"]),
            [UploadFile(filename="test.pdf", file=io.BytesIO(pdf()))],
            "new",
        )


async def test_job_search_rename_reenable_and_http_delete(db, tmp_path):
    bid = await batch(db, tmp_path)
    jid = int((await resumes.batch_detail(db, bid))["job_id"])
    original = (await jobs.detail(db, jid))["versions"][0]["rule_snapshot"]
    updated = await jobs.patch_job(
        db, jid, JobPatch(draft_version=1, name="  手动修改岗位名称  ")
    )
    assert updated["name"] == "手动修改岗位名称"
    assert (await jobs.list_jobs(db, 1, 50, "修改"))["total"] == 1
    assert (await jobs.list_jobs(db, 1, 50, "不存在"))["total"] == 0
    assert (await jobs.detail(db, jid))["versions"][0]["rule_snapshot"] == original
    await jobs.disable(db, jid)
    assert (await jobs.list_jobs(db, 1, 50, status="active"))["total"] == 0
    await jobs.enable(db, jid)
    assert (await jobs.list_jobs(db, 1, 50, status="active"))["items"][0][
        "latest_published_version"
    ] == 1
    app = create_app(config(tmp_path))
    app.state.mysql = db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.delete(f"/api/jobs/{jid}")).status_code == 204
        assert (await client.get("/api/jobs")).json()["total"] == 0
        assert (
            await client.patch(
                f"/api/jobs/{jid}",
                json={"name": "不能恢复已删除岗位", "draft_version": 3},
            )
        ).status_code == 404


async def test_blank_job_name_rejected(db, tmp_path):
    app = create_app(config(tmp_path))
    app.state.mysql = db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post("/api/jobs", json={"name": "   "})).status_code == 422
