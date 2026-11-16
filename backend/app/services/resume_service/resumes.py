import asyncio
import copy
import hashlib
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.agents.resume_evaluation_agent.scoring import new_snapshot
from app.core.errors import BusinessError
from app.models.mysql.entities import (
    ActionRecord,
    Batch,
    Candidate,
    File,
    FileImportTask,
    FilePage,
    Job,
    JobResume,
    JobRuleVersion,
    Reservation,
    Review,
    utcnow,
)
from app.repositories.common import require, serialize
from app.repositories.evaluation_repo.visibility import is_deleted


def safe_path(config, relative):
    root = config.storage_dir.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise BusinessError("文件路径无效", 400)
    return path


async def create_batch(db, config, job_id, version_id, uploads, name):
    if not uploads or len(uploads) > config.upload_max_files:
        raise BusinessError("上传文件数量不符合限制")
    prepared, new_paths = [], []
    commit_pending = False
    try:
        for upload in uploads:
            filename = (
                (upload.filename or "resume.pdf").replace("\\", "/").rsplit("/", 1)[-1]
            )
            data = await upload.read(config.upload_max_mb * 1024 * 1024 + 1)
            if len(data) > config.upload_max_mb * 1024 * 1024:
                raise BusinessError(f"文件过大：{filename}")
            if not filename.lower().endswith(".pdf") or b"%PDF-" not in data[:1024]:
                raise BusinessError(f"文件不是有效 PDF：{filename}")
            # Use a unique path, so rollback cleanup cannot remove another upload's file.
            relative = f"uploads/{uuid4().hex}.pdf"
            path = safe_path(config, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(path.write_bytes, data)
            new_paths.append(path)
            prepared.append(
                (filename, hashlib.sha256(data).hexdigest(), relative, len(data))
            )
        async with db.session() as session:
            job = await require(session, Job, job_id, lock=True)
            version = await require(session, JobRuleVersion, version_id)
            if (
                job.deleted_at is not None
                or job.status != "active"
                or version.job_id != job_id
            ):
                raise BusinessError("岗位已停用或规则版本不属于岗位")
            batch = Batch(
                name=name or f"{job.name} 简历批次",
                job_id=job_id,
                rule_version_id=version_id,
                rule_snapshot=new_snapshot(version.rule_snapshot),
            )
            session.add(batch)
            await session.flush()
            seen = set()
            retained = set()
            for filename, digest, relative, size in prepared:
                if digest in seen:
                    continue
                seen.add(digest)
                file = await session.scalar(select(File).where(File.sha256 == digest))
                if file is None:
                    try:
                        async with session.begin_nested():
                            file = File(
                                sha256=digest,
                                original_name=filename,
                                storage_path=relative,
                                size_bytes=size,
                            )
                            session.add(file)
                            await session.flush()
                        retained.add(relative)
                    except IntegrityError:
                        file = await session.scalar(
                            select(File).where(File.sha256 == digest).with_for_update()
                        )
                        if file is None:
                            raise
                session.add(
                    Candidate(
                        batch_id=batch.id,
                        file_id=file.id,
                        original_filename=filename,
                        workflow_id=uuid4().hex,
                    )
                )
                link = await session.scalar(
                    select(JobResume).where(
                        JobResume.job_id == job_id, JobResume.file_id == file.id
                    )
                )
                if link is None:
                    session.add(
                        JobResume(job_id=job_id, file_id=file.id, display_name=filename)
                    )
                else:
                    link.deleted_at = None
            await session.flush()
            result = serialize(batch)
            result["imported_count"] = len(seen)
            commit_pending = True
        # Database commit succeeded before removing unused temporary copies.
        for path in new_paths:
            if (
                path.relative_to(config.storage_dir.resolve()).as_posix()
                not in retained
            ):
                path.unlink(missing_ok=True)
        return result
    except BaseException:
        if not commit_pending:
            for path in new_paths:
                path.unlink(missing_ok=True)
        raise
    finally:
        for upload in uploads:
            await upload.close()


async def batch_detail(db, batch_id):
    async with db.session() as session:
        batch = await require(session, Batch, batch_id)
        result = serialize(batch)
        rows = await session.execute(
            select(Candidate.processing_status, func.count())
            .where(Candidate.batch_id == batch_id)
            .group_by(Candidate.processing_status)
        )
        counts = dict(rows.all())
        result["progress"] = {
            s: counts.get(s, 0)
            for s in ("pending", "running", "waiting_review", "completed", "failed")
        }
        result["total"] = sum(counts.values())
        return result


async def candidates(
    db, batch_id, status=None, recommendation=None, page=1, page_size=50
):
    async with db.session() as session:
        await require(session, Batch, batch_id)
        query = select(Candidate).where(Candidate.batch_id == batch_id)
        if status:
            query = query.where(Candidate.processing_status == status)
        if recommendation:
            query = query.where(Candidate.recommendation == recommendation)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        rows = (
            await session.scalars(
                query.order_by(Candidate.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return {"items": [serialize(r) for r in rows], "total": total}


async def candidate_detail(db, candidate_id):
    async with db.session() as session:
        candidate = await require(session, Candidate, candidate_id)
        batch = await require(session, Batch, candidate.batch_id)
        result = serialize(candidate)
        result["deleted"] = await is_deleted(session, candidate_id)
        result.update(
            job_id=str(batch.job_id), rule_version_id=str(batch.rule_version_id)
        )
        result["rule_snapshot"] = batch.rule_snapshot
        result["review_history"] = [
            serialize(r)
            for r in (
                await session.scalars(
                    select(Review)
                    .where(Review.candidate_id == candidate_id)
                    .order_by(Review.id)
                )
            ).all()
        ]
        reservation = await session.scalar(
            select(Reservation).where(Reservation.candidate_id == candidate_id)
        )
        result["reservation"] = serialize(reservation) if reservation else None
        result["actions"] = (
            [
                serialize(r)
                for r in (
                    await session.scalars(
                        select(ActionRecord).where(
                            ActionRecord.reservation_id == reservation.id
                        )
                    )
                ).all()
            ]
            if reservation
            else []
        )
        return result


async def read_parsed_content(db, config, file_id):
    """Read immutable parser output. New full-document results do not use page numbers."""
    async with db.session() as session:
        file = await require(session, File, file_id)
        if file.parse_status != "completed":
            raise BusinessError("简历尚未解析完成，请先完成导入解析", 409)
        if file.normalized_markdown_path:
            if not file.normalized_markdown_path:
                raise BusinessError("解析正文缺失，请重新解析", 409)
            path = safe_path(config, file.normalized_markdown_path)
            try:
                text = await asyncio.to_thread(path.read_text, encoding="utf-8")
            except OSError:
                raise BusinessError("解析正文缺失，请重新解析", 409) from None
            return [
                {
                    "file_id": str(file_id),
                    "block_id": "document",
                    "page_no": None,
                    "text": text,
                }
            ]
        # Old results remain readable without rewriting published evidence.
        rows = (
            await session.scalars(
                select(FilePage)
                .where(FilePage.file_id == file_id)
                .order_by(FilePage.page_no)
            )
        ).all()
        if not rows:
            raise BusinessError("解析正文缺失，请重新解析", 409)
        return [
            {
                "file_id": str(file_id),
                "page_no": r.page_no,
                "text": await asyncio.to_thread(
                    safe_path(config, r.text_path).read_text, encoding="utf-8"
                ),
            }
            for r in rows
        ]


async def parse_pdf(
    db,
    config,
    file_id,
    *,
    finalize=True,
    parser=None,
    task_id=None,
):
    import json

    from app.clients.pdf_client import PDFClient

    async with db.session() as session:
        file = await require(session, File, file_id)
        cached = file.parse_status == "completed"
        if not cached and file.file_type != "pdf":
            raise BusinessError("当前仅支持 PDF 简历，请上传 PDF")
        path, expected_hash = safe_path(config, file.storage_path), file.sha256
    if cached:
        return await read_parsed_content(db, config, file_id)
    from app.services.resume_service.workspace import file_sha

    if await asyncio.to_thread(file_sha, path) != expected_hash:
        raise BusinessError("原件 SHA-256 校验失败，请重新上传原件", 409)
    client = parser if parser is not None else PDFClient()
    try:
        document_text = await client.extract(path)
        snapshot_id = str(task_id) if task_id is not None else uuid4().hex
        root = f"parsed/{file_id}/imports/{snapshot_id}"
        paths = {
            "markdown_path": f"{root}/document.md",
            "normalized_markdown_path": f"{root}/normalized.md",
            "source_index_path": f"{root}/sources.json",
        }
        normalized = document_text.strip()
        index = [
            {
                "file_id": str(file_id),
                "block_id": "document",
                "text_path": paths["normalized_markdown_path"],
                "sha256": hashlib.sha256(normalized.encode()).hexdigest(),
            }
        ]
        for key, content in (
            ("markdown_path", document_text),
            ("normalized_markdown_path", normalized),
            ("source_index_path", json.dumps(index, ensure_ascii=False)),
        ):
            target = safe_path(config, paths[key])
            target.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(target.write_text, content, encoding="utf-8")
        async with db.session() as session:
            file = await require(session, File, file_id, lock=True)
            for key, value in paths.items():
                setattr(file, key, value)
            file.parser_name, file.parser_version = (
                "pymupdf-text",
                client.version,
            )
            file.page_count = None
            if task_id is not None:
                task = await require(session, FileImportTask, task_id, lock=True)
                progress = copy.deepcopy(task.node_progress or [])
                for node in progress:
                    if node["name"] == "parse_pdf":
                        node["artifact"] = {
                            **paths,
                            "parser_name": file.parser_name,
                            "parser_version": file.parser_version,
                            "source_sha256": expected_hash,
                            "text_sha256": hashlib.sha256(
                                normalized.encode()
                            ).hexdigest(),
                            "char_count": len(normalized),
                        }
                task.node_progress = progress
            file.parse_status, file.parse_error, file.parsed_at = (
                "completed" if finalize else "running",
                None,
                utcnow(),
            )
        return [
            {
                "file_id": str(file_id),
                "block_id": "document",
                "page_no": None,
                "text": normalized,
            }
        ]
    except (BusinessError, OSError) as exc:
        async with db.session() as session:
            file = await require(session, File, file_id)
            file.parse_status, file.parse_error = (
                "failed",
                exc.message if isinstance(exc, BusinessError) else "解析产物保存失败",
            )
        raise
