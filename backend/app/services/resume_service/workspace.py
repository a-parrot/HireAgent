"""Per-job resume management; originals and historical evaluations are retained."""

import asyncio
import hashlib
import re
from contextlib import AsyncExitStack
from pathlib import Path
from uuid import uuid4

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError

from app.agents.resume_evaluation_agent.scoring import new_snapshot
from app.core.errors import BusinessError
from app.models.mysql.entities import (
    ActionRecord,
    Batch,
    Candidate,
    Event,
    File,
    FileImportTask,
    FilePage,
    Job,
    JobResume,
    JobRuleVersion,
    NodeExecution,
    Reservation,
    Slot,
    utcnow,
)
from app.repositories.common import require, serialize
from app.repositories.evaluation_repo.visibility import (
    DELETED_EVENT,
    is_deleted,
    visible_candidates,
)
from app.repositories.job_repo.jobs import get_job
from app.services.resume_service.resumes import safe_path
from app.services.schedule_service.scheduling import calendar_lock


def file_sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


async def job_summary(db):
    async with db.session() as s:
        rows = (
            await s.execute(
                select(
                    Job,
                    func.count(JobResume.id),
                    func.sum(case((File.parse_status == "completed", 1), else_=0)),
                )
                .outerjoin(
                    JobResume,
                    (JobResume.job_id == Job.id) & JobResume.deleted_at.is_(None),
                )
                .outerjoin(File, File.id == JobResume.file_id)
                .where(Job.deleted_at.is_(None))
                .group_by(Job.id)
                .order_by(Job.id.desc())
            )
        ).all()
        return {
            "items": [
                {**serialize(j), "resume_count": n, "parsed_count": int(ready or 0)}
                for j, n, ready in rows
            ]
        }


async def list_resumes(
    db, job_id, page=1, page_size=20, keyword=None, status=None, evaluation_status=None
):
    async with db.session() as s:
        await get_job(s, job_id)
        q = (
            select(JobResume, File)
            .join(File, File.id == JobResume.file_id)
            .where(JobResume.job_id == job_id, JobResume.deleted_at.is_(None))
        )
        if keyword:
            q = q.where(JobResume.display_name.contains(keyword, autoescape=True))
        if status:
            q = q.where(File.parse_status == status)
        if evaluation_status:
            latest_id = (
                select(func.max(Candidate.id))
                .join(Batch, Batch.id == Candidate.batch_id)
                .where(Batch.job_id == job_id, Candidate.file_id == File.id)
                .correlate(File)
                .scalar_subquery()
            )
            active = (
                select(Candidate.id)
                .join(Batch, Batch.id == Candidate.batch_id)
                .where(Candidate.id == latest_id, visible_candidates())
            )
            if evaluation_status == "none":
                q = q.where(~active.exists())
            else:
                if evaluation_status == "queued":
                    active = active.where(
                        Candidate.processing_status == "pending",
                        Batch.started_at.is_not(None),
                    )
                elif evaluation_status == "pending":
                    active = active.where(
                        Candidate.processing_status == "pending",
                        Batch.started_at.is_(None),
                    )
                else:
                    active = active.where(
                        Candidate.processing_status == evaluation_status
                    )
                q = q.where(active.exists())
        total = await s.scalar(select(func.count()).select_from(q.subquery()))
        rows = (
            await s.execute(
                q.order_by(JobResume.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        latest = await latest_evaluations(s, job_id, [f.id for _, f in rows])
        return {
            "items": [
                {
                    **serialize(f),
                    "id": str(r.id),
                    "file_id": str(f.id),
                    "display_name": r.display_name,
                    "added_at": serialize(r)["created_at"],
                    "latest_evaluation": latest.get(f.id),
                }
                for r, f in rows
            ],
            "total": total,
        }


async def latest_evaluations(s, job_id, file_ids):
    if not file_ids:
        return {}
    ids = (
        select(func.max(Candidate.id))
        .join(Batch, Batch.id == Candidate.batch_id)
        .where(Batch.job_id == job_id, Candidate.file_id.in_(file_ids))
        .group_by(Candidate.file_id)
    )
    rows = (
        await s.execute(
            select(
                Candidate.id,
                Candidate.file_id,
                Candidate.processing_status,
                Candidate.total_score,
                Candidate.recommendation,
                Candidate.error_message,
                Candidate.current_node,
                Candidate.updated_at,
                Candidate.schedule_status,
                Candidate.waitlist_reason,
                Batch.started_at,
            )
            .join(Batch, Batch.id == Candidate.batch_id)
            .where(Candidate.id.in_(ids), visible_candidates())
        )
    ).all()
    progress = {}
    if rows:
        running_nodes = (
            await s.execute(
                select(NodeExecution.candidate_id, NodeExecution.output_data).where(
                    NodeExecution.candidate_id.in_([r.id for r in rows]),
                    NodeExecution.status == "running",
                )
            )
        ).all()
        progress = {
            cid: output.get("progress")
            for cid, output in running_nodes
            if isinstance(output, dict)
        }
    return {
        r.file_id: {
            "id": str(r.id),
            "processing_status": r.processing_status,
            "total_score": float(r.total_score) if r.total_score is not None else None,
            "recommendation": r.recommendation,
            "error_message": r.error_message,
            "current_node": r.current_node,
            "progress": progress.get(r.id),
            "updated_at": r.updated_at.isoformat() + "Z" if r.updated_at else None,
            "schedule_status": r.schedule_status,
            "waitlist_reason": r.waitlist_reason,
            "queued": r.started_at is not None,
        }
        for r in rows
    }


async def link_file(s, job_id, file, filename):
    # Locking the job serializes workspace changes for the same job.
    row = await s.scalar(
        select(JobResume).where(
            JobResume.job_id == job_id, JobResume.file_id == file.id
        )
    )
    duplicate = row is not None and row.deleted_at is None
    if row is None:
        row = JobResume(job_id=job_id, file_id=file.id, display_name=filename)
        s.add(row)
    elif not duplicate:
        row.deleted_at = None
        row.display_name = filename
    await s.flush()
    return row, duplicate


async def queue_file(s, file):
    if file.parse_status == "completed":
        return None
    task = await s.scalar(
        select(FileImportTask)
        .where(
            FileImportTask.file_id == file.id,
            FileImportTask.status.in_(["pending", "running"]),
        )
        .order_by(FileImportTask.id.desc())
        .limit(1)
    )
    if task is None:
        task = FileImportTask(task_id=uuid4().hex, file_id=file.id, node_progress=[])
        s.add(task)
        file.parse_status, file.parse_error = "pending", None
        await s.flush()
    return task.id


async def upload_one(db, config, job_id, upload, expected=None):
    filename = (upload.filename or "resume.pdf").replace("\\", "/").rsplit("/", 1)[-1]
    if len(filename) > 255:
        raise BusinessError("文件名不能超过 255 个字符")
    suffix = Path(filename).suffix.lower()
    if suffix != ".pdf":
        raise BusinessError("仅支持 PDF 简历")
    data = await upload.read(config.upload_max_mb * 1024 * 1024 + 1)
    if not data or len(data) > config.upload_max_mb * 1024 * 1024:
        raise BusinessError(f"文件为空或超过 {config.upload_max_mb} MB")
    digest = hashlib.sha256(data).hexdigest()
    if expected and (
        not re.fullmatch(r"[0-9a-fA-F]{64}", expected) or expected.lower() != digest
    ):
        raise BusinessError("SHA-256 校验失败，文件未被接收")
    if suffix == ".pdf" and b"%PDF-" not in data[:1024]:
        raise BusinessError("文件内容不是有效 PDF")
    relative = f"uploads/{uuid4().hex}{suffix}"
    path = safe_path(config, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_bytes, data)
    keep = False
    commit_pending = False
    try:
        async with db.session() as s:
            job = await get_job(s, job_id, lock=True)
            if job.status != "active":
                raise BusinessError("岗位已停用，请先启用")
            file = await s.scalar(select(File).where(File.sha256 == digest))
            if file is None:
                try:
                    async with s.begin_nested():
                        file = File(
                            sha256=digest,
                            original_name=filename,
                            storage_path=relative,
                            size_bytes=len(data),
                            file_type=suffix[1:],
                            media_type="application/pdf",
                        )
                        s.add(file)
                        await s.flush()
                    keep = True
                except IntegrityError:
                    file = await s.scalar(
                        select(File).where(File.sha256 == digest).with_for_update()
                    )
                    if file is None:
                        raise
            # Serialize task enqueue for files shared across jobs.
            file = await require(s, File, file.id, lock=True)
            if not keep:
                try:
                    intact = (
                        await asyncio.to_thread(
                            file_sha, safe_path(config, file.storage_path)
                        )
                        == digest
                    )
                except OSError:
                    intact = False
                if not intact:
                    # The uploaded bytes match the registered hash and can restore a damaged original.
                    file.storage_path = relative
                    file.parse_status, file.parse_error = "pending", None
                    keep = True
            row, duplicate = await link_file(s, job_id, file, filename)
            tid = await queue_file(s, file)
            result = {
                "filename": filename,
                "resume_id": str(row.id),
                "file_id": str(file.id),
                "sha256": digest,
                "result": "duplicate" if duplicate else "accepted",
                "parse_status": file.parse_status,
                "message": "该岗位已有相同内容的简历"
                if duplicate
                else "SHA-256 校验通过",
            }
            commit_pending = True
        return result, tid
    finally:
        if not keep or not commit_pending:
            path.unlink(missing_ok=True)


async def upload_many(db, config, job_id, uploads, hashes=None):
    if not uploads or len(uploads) > config.upload_max_files:
        raise BusinessError(f"请选择 1 至 {config.upload_max_files} 个文件")
    if hashes and len(hashes) != len(uploads):
        raise BusinessError("SHA-256 数量必须与文件数量相同")
    async with db.session() as s:
        job = await get_job(s, job_id)
        if job.status != "active":
            raise BusinessError("岗位已停用，请先启用")
    items, tasks = [], []
    try:
        for i, upload in enumerate(uploads):
            try:
                item, tid = await upload_one(
                    db, config, job_id, upload, hashes[i] if hashes else None
                )
                items.append(item)
                if tid:
                    tasks.append(tid)
            except BusinessError as exc:
                items.append(
                    {
                        "filename": upload.filename or "",
                        "result": "rejected",
                        "message": exc.message,
                    }
                )
    finally:
        for upload in uploads:
            await upload.close()
    return {
        "items": items,
        "accepted": sum(x["result"] == "accepted" for x in items),
        "duplicates": sum(x["result"] == "duplicate" for x in items),
        "rejected": sum(x["result"] == "rejected" for x in items),
    }, list(dict.fromkeys(tasks))


async def resume_row(s, job_id, resume_id, lock=False):
    await get_job(s, job_id)
    row = await require(s, JobResume, resume_id, lock=lock)
    if row.job_id != job_id or row.deleted_at is not None:
        raise BusinessError("简历不存在或已移除", 404)
    return row


async def detail(db, config, job_id, resume_id):
    async with db.session() as s:
        row = await resume_row(s, job_id, resume_id)
        file = await require(s, File, row.file_id)
        result = {
            **serialize(file),
            "id": str(row.id),
            "file_id": str(file.id),
            "display_name": row.display_name,
            "added_at": serialize(row)["created_at"],
        }
        pages = (
            await s.scalars(
                select(FilePage)
                .where(FilePage.file_id == file.id)
                .order_by(FilePage.page_no)
            )
        ).all()
        task = await s.scalar(
            select(FileImportTask)
            .where(FileImportTask.file_id == file.id)
            .order_by(FileImportTask.id.desc())
            .limit(1)
        )
        result["import_task"] = serialize(task) if task else None
        history = (
            await s.execute(
                select(
                    Candidate.id,
                    Batch.id.label("batch_id"),
                    Batch.name,
                    Candidate.processing_status,
                    Candidate.recommendation,
                    Candidate.total_score,
                    Candidate.created_at,
                )
                .join(Batch, Batch.id == Candidate.batch_id)
                .where(
                    Batch.job_id == job_id,
                    Candidate.file_id == file.id,
                    visible_candidates(),
                )
                .order_by(Candidate.id.desc())
            )
        ).all()
        result["evaluations"] = [
            {
                **dict(r._mapping),
                "id": str(r.id),
                "batch_id": str(r.batch_id),
                "total_score": float(r.total_score)
                if r.total_score is not None
                else None,
                "created_at": r.created_at.isoformat() + "Z",
            }
            for r in history
        ]
        path = safe_path(config, file.storage_path)
    try:
        result["sha256_verified"] = (
            await asyncio.to_thread(file_sha, path) == file.sha256
        )
    except OSError:
        result["sha256_verified"] = False
    result["markdown"] = None
    if file.normalized_markdown_path:
        try:
            result["markdown"] = await asyncio.to_thread(
                safe_path(config, file.normalized_markdown_path).read_text,
                encoding="utf-8",
            )
        except OSError:
            result["markdown"] = None
    result["pages"] = []
    for page in pages:
        try:
            text = await asyncio.to_thread(
                safe_path(config, page.text_path).read_text, encoding="utf-8"
            )
        except OSError:
            text = "解析文本缺失，请重新解析"
        result["pages"].append({"page_no": page.page_no, "text": text})
    return result


async def remove(db, job_id, resume_id, runtime=None):
    async with calendar_lock, AsyncExitStack() as stack, db.session() as s:
        await get_job(s, job_id, lock=True)
        row = await resume_row(s, job_id, resume_id, lock=True)
        candidates = (
            await s.scalars(
                select(Candidate)
                .join(Batch, Batch.id == Candidate.batch_id)
                .where(Batch.job_id == job_id, Candidate.file_id == row.file_id)
                .order_by(Candidate.id)
            )
        ).all()
        for candidate in candidates:
            if runtime is not None:
                lock = runtime.locks.setdefault(candidate.id, asyncio.Lock())
                if lock.locked():
                    raise BusinessError("关联评估仍在处理中，请等待完成后删除", 409)
                await stack.enter_async_context(lock)
            if candidate.processing_status == "running":
                raise BusinessError("关联评估仍在处理中，请等待完成后删除", 409)
        # Lock and validate the whole dependency set before modifying any record.
        reservations = (
            await s.scalars(
                select(Reservation)
                .where(Reservation.candidate_id.in_([c.id for c in candidates]))
                .with_for_update()
            )
        ).all()
        actions = (
            (
                await s.scalars(
                    select(ActionRecord)
                    .where(
                        ActionRecord.reservation_id.in_([r.id for r in reservations])
                    )
                    .with_for_update()
                )
            ).all()
            if reservations
            else []
        )
        if any(
            a.attempt_count or a.status in ("running", "succeeded", "uncertain")
            for a in actions
        ):
            raise BusinessError(
                "关联预约已有会议或通知执行记录，请先核实外部安排，当前简历及关联数据均未删除",
                409,
            )
        for reservation in reservations:
            slot = await require(s, Slot, reservation.slot_id, lock=True)
            s.add(
                Event(
                    batch_id=reservation.batch_id,
                    candidate_id=reservation.candidate_id,
                    event_type="interview_cancelled",
                    message="删除岗位简历，级联取消面试预约",
                    details={
                        "reservation": serialize(reservation),
                        "slot": serialize(slot),
                    },
                )
            )
        for action in actions:
            await s.delete(action)
        await s.flush()
        slot_ids = [r.slot_id for r in reservations]
        for reservation in reservations:
            await s.delete(reservation)
        await s.flush()
        for slot_id in slot_ids:
            await s.delete(await require(s, Slot, slot_id))
        for candidate in candidates:
            if not await is_deleted(s, candidate.id):
                s.add(
                    Event(
                        batch_id=candidate.batch_id,
                        candidate_id=candidate.id,
                        event_type=DELETED_EVENT,
                        message="删除岗位简历，级联删除关联评估及面试排期",
                        details={"job_id": str(job_id), "resume_id": str(resume_id)},
                    )
                )
            candidate.schedule_status, candidate.waitlist_reason = "unscheduled", None
        row.deleted_at = utcnow()
        await s.flush()
        for batch_id in sorted({c.batch_id for c in candidates}):
            batch = await require(s, Batch, batch_id, lock=True)
            active = await s.scalar(
                select(Candidate.id)
                .where(
                    Candidate.batch_id == batch_id,
                    Candidate.processing_status.in_(["pending", "running"]),
                    visible_candidates(),
                )
                .limit(1)
            )
            batch.status = "running" if active else "evaluation_done"
            if not active:
                batch.evaluation_completed_at = (
                    batch.evaluation_completed_at or utcnow()
                )


async def retry(db, job_id, resume_id):
    async with db.session() as s:
        row = await resume_row(s, job_id, resume_id)
        file = await require(s, File, row.file_id, lock=True)
        if file.parse_status == "completed":
            file.parse_status = "pending"
        return await queue_file(s, file)


async def create_evaluation(
    db,
    job_id,
    resume_ids,
    version_id,
    name=None,
    *,
    config=None,
    evaluation_key=None,
    allow_unparsed=False,
):
    if not resume_ids or len(set(resume_ids)) != len(resume_ids):
        raise BusinessError("请选择不重复的简历")
    async with db.session() as s:
        job = await get_job(s, job_id, lock=True)
        version = await require(s, JobRuleVersion, version_id)
        if job.status != "active" or version.job_id != job_id:
            raise BusinessError("岗位已停用或规则版本不属于岗位")
        rows = (
            await s.execute(
                select(JobResume, File)
                .join(File, File.id == JobResume.file_id)
                .where(
                    JobResume.id.in_(resume_ids),
                    JobResume.job_id == job_id,
                    JobResume.deleted_at.is_(None),
                )
            )
        ).all()
        if len(rows) != len(resume_ids):
            raise BusinessError("部分简历已移除或不属于当前岗位")
        if not allow_unparsed and any(f.parse_status != "completed" for _, f in rows):
            raise BusinessError("请仅选择解析完成的简历")
        if config is not None:
            for _, file in rows:
                try:
                    intact = (
                        await asyncio.to_thread(
                            file_sha, safe_path(config, file.storage_path)
                        )
                        == file.sha256
                    )
                except OSError:
                    intact = False
                if not intact:
                    raise BusinessError(
                        "原件 SHA-256 校验失败，请重新上传对应原件", 409
                    )
        if evaluation_key:
            existing = await s.scalar(
                select(Batch)
                .join(Event, Event.batch_id == Batch.id)
                .where(
                    Batch.job_id == job_id,
                    Event.event_type == "evaluation_request",
                    Event.message == evaluation_key,
                )
            )
            if existing:
                existing_files = set(
                    await s.scalars(
                        select(Candidate.file_id).where(
                            Candidate.batch_id == existing.id
                        )
                    )
                )
                if existing.rule_version_id != version_id or existing_files != {
                    f.id for _, f in rows
                }:
                    raise BusinessError("同一评估请求不能更换简历或规则", 409)
                return {**serialize(existing), "imported_count": len(rows)}
        batch = Batch(
            job_id=job_id,
            rule_version_id=version_id,
            rule_snapshot=new_snapshot(version.rule_snapshot),
            name=name or f"{job.name} 简历评估",
        )
        s.add(batch)
        await s.flush()
        if evaluation_key:
            s.add(
                Event(
                    batch_id=batch.id,
                    event_type="evaluation_request",
                    message=evaluation_key,
                )
            )
        for row, file in rows:
            s.add(
                Candidate(
                    batch_id=batch.id,
                    file_id=file.id,
                    original_filename=row.display_name,
                    workflow_id=uuid4().hex,
                )
            )
        return {**serialize(batch), "imported_count": len(rows)}
