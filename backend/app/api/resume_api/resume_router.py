from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.core.errors import BusinessError
from app.models.mysql.entities import Batch, File
from app.repositories.common import require, serialize
from app.services.resume_service import resumes

router = APIRouter(prefix="/api", tags=["简历"])


@router.get("/batches")
async def list_batches(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    async with request.app.state.mysql.session() as session:
        total = await session.scalar(select(func.count()).select_from(Batch))
        rows = (
            await session.scalars(
                select(Batch)
                .order_by(Batch.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return {"items": [serialize(row) for row in rows], "total": total}


@router.get("/batches/{batch_id}")
async def batch(request: Request, batch_id: int):
    return await resumes.batch_detail(request.app.state.mysql, batch_id)


@router.get("/candidates")
async def candidates(
    request: Request,
    batch_id: int,
    status: str | None = None,
    recommendation: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    return await resumes.candidates(
        request.app.state.mysql, batch_id, status, recommendation, page, page_size
    )


@router.get("/candidates/{candidate_id}")
async def candidate(request: Request, candidate_id: int):
    return await resumes.candidate_detail(request.app.state.mysql, candidate_id)


@router.get("/files/{file_id}")
async def original(request: Request, file_id: int):
    async with request.app.state.mysql.session() as session:
        file = await require(session, File, file_id)
        path = resumes.safe_path(request.app.state.settings, file.storage_path)
        filename = file.original_name
    if not path.is_file():
        raise BusinessError("PDF 原件缺失，请恢复备份", 404)
    return FileResponse(
        path,
        media_type=file.media_type,
        filename=filename,
        content_disposition_type="inline" if file.file_type == "pdf" else "attachment",
    )


@router.get("/files/{file_id}/preview")
async def preview(request: Request, file_id: int):
    async with request.app.state.mysql.session() as session:
        file = await require(session, File, file_id)
        relative = (
            file.storage_path if file.file_type == "pdf" else file.preview_pdf_path
        )
        if not relative:
            raise BusinessError("预览文件尚未生成", 404)
        path = resumes.safe_path(request.app.state.settings, relative)
    if not path.is_file():
        raise BusinessError("预览文件缺失", 404)
    return FileResponse(
        path, media_type="application/pdf", content_disposition_type="inline"
    )


@router.get("/files/{file_id}/content")
async def parsed_content(request: Request, file_id: int):
    sources = await resumes.read_parsed_content(
        request.app.state.mysql, request.app.state.settings, file_id
    )
    return {
        "file_id": str(file_id),
        "markdown": "\n\n".join(source["text"] for source in sources),
    }
