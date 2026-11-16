"""Validate the local PDF and original SHA before parsing."""

import asyncio

from app.core.errors import BusinessError
from app.models.mysql.entities import File
from app.repositories.common import require
from app.services.resume_service.resumes import safe_path
from app.services.resume_service.workspace import file_sha


async def run(runtime, state):
    async with runtime.db.session() as session:
        file = await require(session, File, state["file_id"])
        source = safe_path(runtime.config, file.storage_path)
        file_type, digest = file.file_type, file.sha256
    if file_type != "pdf":
        raise BusinessError("当前仅支持 PDF 简历，请上传 PDF")
    if await asyncio.to_thread(file_sha, source) != digest:
        raise BusinessError("原件 SHA-256 与入库记录不一致，停止解析，请重新上传原件")
    return {"file_type": "pdf"}
