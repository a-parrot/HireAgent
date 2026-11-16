from typing import Literal

from fastapi import APIRouter, Query, Request

from app.services.history_service import history

router = APIRouter(prefix="/api/history", tags=["历史记录与日志"])


@router.get("/imports")
async def imports(
    request: Request,
    job_id: int | None = Query(None, gt=0),
    file_id: int | None = Query(None, gt=0),
    keyword: str | None = Query(None, max_length=255),
    status: Literal["pending", "running", "completed", "failed"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    return await history.imports(
        request.app.state.mysql,
        job_id=job_id,
        file_id=file_id,
        keyword=keyword,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/imports/{task_id}")
async def import_detail(request: Request, task_id: int):
    return await history.import_detail(
        request.app.state.mysql, request.app.state.settings, task_id
    )


@router.get("/evaluations")
async def evaluations(
    request: Request,
    job_id: int | None = Query(None, gt=0),
    keyword: str | None = Query(None, max_length=255),
    status: Literal["pending", "running", "evaluation_done", "failed"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    return await history.evaluations(
        request.app.state.mysql,
        job_id=job_id,
        keyword=keyword,
        status=status,
        page=page,
        page_size=page_size,
    )
