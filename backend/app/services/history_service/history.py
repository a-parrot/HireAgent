"""Read-only parsing history and evaluation logs, independent from scheduling."""

import asyncio
import hashlib

from sqlalchemy import func, or_, select

from app.models.mysql.entities import (
    Batch,
    Candidate,
    File,
    FileImportTask,
    Job,
    JobResume,
)
from app.repositories.common import require, serialize
from app.services.resume_service.resumes import safe_path


async def imports(
    db, *, job_id=None, file_id=None, keyword=None, status=None, page=1, page_size=20
):
    query = select(FileImportTask, File.original_name).join(File)
    if job_id is not None:
        query = query.where(
            FileImportTask.file_id.in_(
                select(JobResume.file_id).where(JobResume.job_id == job_id)
            )
        )
    if file_id is not None:
        query = query.where(FileImportTask.file_id == file_id)
    if keyword:
        query = query.where(
            or_(
                File.original_name.contains(keyword, autoescape=True),
                FileImportTask.task_id.contains(keyword, autoescape=True),
            )
        )
    if status:
        query = query.where(FileImportTask.status == status)
    async with db.session() as session:
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        rows = (
            await session.execute(
                query.order_by(FileImportTask.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return {
            "items": [
                {
                    **serialize(task),
                    "filename": filename,
                    "has_snapshot": any(
                        bool(n.get("artifact")) for n in task.node_progress or []
                    ),
                }
                for task, filename in rows
            ],
            "total": total,
        }


async def import_detail(db, config, task_id):
    async with db.session() as session:
        task = await require(session, FileImportTask, task_id)
        file = await require(session, File, task.file_id)
        result = {
            **serialize(task),
            "filename": file.original_name,
            "source_sha256": file.sha256,
            "markdown": None,
            "artifact_error": None,
        }
        artifact = next(
            (n["artifact"] for n in task.node_progress or [] if n.get("artifact")), None
        )
        result["artifact"] = artifact
        result["has_snapshot"] = artifact is not None
    if artifact is None:
        result["artifact_error"] = (
            "此历史记录仅保留日志，旧版本未保存独立正文快照"
            if task.status == "completed"
            else "本次解析尚未生成正文快照"
        )
        return result
    try:
        text = await asyncio.to_thread(
            safe_path(config, artifact["normalized_markdown_path"]).read_text,
            encoding="utf-8",
        )
        if hashlib.sha256(text.encode()).hexdigest() != artifact["text_sha256"]:
            result["artifact_error"] = "历史正文快照校验失败，请检查存储文件"
        else:
            result["markdown"] = text
    except OSError:
        result["artifact_error"] = "历史正文快照文件缺失，日志仍可查看"
    return result


async def evaluations(
    db, *, job_id=None, keyword=None, status=None, page=1, page_size=20
):
    query = select(Batch, Job.name).select_from(Batch).join(Job, Job.id == Batch.job_id)
    if job_id is not None:
        query = query.where(Batch.job_id == job_id)
    if keyword:
        query = query.where(
            or_(
                Batch.name.contains(keyword, autoescape=True),
                Job.name.contains(keyword, autoescape=True),
            )
        )
    if status == "failed":
        query = query.where(
            Batch.id.in_(
                select(Candidate.batch_id).where(
                    Candidate.processing_status == "failed"
                )
            )
        )
    elif status:
        query = query.where(Batch.status == status)
    async with db.session() as session:
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        rows = (
            await session.execute(
                query.order_by(Batch.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        ids = [b.id for b, _ in rows]
        stats = (
            (
                await session.execute(
                    select(
                        Candidate.batch_id, Candidate.processing_status, func.count()
                    )
                    .where(Candidate.batch_id.in_(ids))
                    .group_by(Candidate.batch_id, Candidate.processing_status)
                )
            ).all()
            if ids
            else []
        )
        counts = {}
        for bid, state, count in stats:
            counts.setdefault(bid, {})[state] = count
        return {
            "items": [
                {
                    **serialize(b),
                    "job_name": name,
                    "progress": counts.get(b.id, {}),
                    "total": sum(counts.get(b.id, {}).values()),
                }
                for b, name in rows
            ],
            "total": total,
        }
