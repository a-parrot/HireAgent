import asyncio
import hashlib
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.errors import BusinessError
from app.models.mysql.entities import (
    ActionRecord,
    Batch,
    Candidate,
    File,
    FilePage,
    Job,
    JobResume,
    JobRuleVersion,
    Reservation,
    Review,
    utcnow,
)
from app.repositories.common import require, serialize


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
                rule_snapshot=version.rule_snapshot,
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
        result.update(
            job_id=str(batch.job_id), rule_version_id=str(batch.rule_version_id)
        )
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


def extract_pdf(path):
    import pymupdf

    try:
        with pymupdf.open(path) as document:
            if document.needs_pass:
                raise BusinessError("PDF 已加密，需人工处理")
            pages = [p.get_text() for p in document]
        if not pages or not any(p.strip() for p in pages):
            raise BusinessError("PDF 无可读文本，需人工处理扫描件")
        return pages
    except BusinessError:
        raise
    except (RuntimeError, ValueError) as exc:
        raise BusinessError("PDF 损坏或无法读取") from exc


async def parse_pdf(db, config, file_id, *, finalize=True):
    async with db.session() as session:
        file = await require(session, File, file_id)
        if file.parse_status == "completed":
            rows = (
                await session.scalars(
                    select(FilePage)
                    .where(FilePage.file_id == file_id)
                    .order_by(FilePage.page_no)
                )
            ).all()
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
        path = safe_path(
            config,
            file.preview_pdf_path
            if file.file_type == "docx" and file.preview_pdf_path
            else file.storage_path,
        )
    try:
        texts = await asyncio.to_thread(extract_pdf, path)
        outputs = []
        for index, text in enumerate(texts, 1):
            relative = f"page_texts/{file_id}/{index}.txt"
            target = safe_path(config, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(target.write_text, text, encoding="utf-8")
            outputs.append((index, relative, text))
        async with db.session() as session:
            file = await require(session, File, file_id, lock=True)
            for index, relative, text in outputs:
                page = await session.scalar(
                    select(FilePage).where(
                        FilePage.file_id == file_id, FilePage.page_no == index
                    )
                )
                if page is None:
                    page = FilePage(file_id=file_id, page_no=index)
                    session.add(page)
                page.text_path, page.text_sha256, page.char_count = (
                    relative,
                    hashlib.sha256(text.encode()).hexdigest(),
                    len(text),
                )
            file.parse_status, file.page_count, file.parse_error = (
                "completed" if finalize else "running",
                len(texts),
                None,
            )
            file.parsed_at = utcnow()
        return [
            {"file_id": str(file_id), "page_no": i, "text": t} for i, _, t in outputs
        ]
    except (BusinessError, OSError):
        async with db.session() as session:
            file = await require(session, File, file_id)
            file.parse_status, file.parse_error = (
                "failed",
                "PDF 解析失败，请检查原件或扫描件",
            )
        raise
