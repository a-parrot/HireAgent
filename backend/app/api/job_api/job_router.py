from typing import Literal

from fastapi import APIRouter, Query, Request, Response

from app.schemas.business import JobCreate, JobPatch, PublishRequest
from app.services.job_service import jobs

router = APIRouter(prefix="/api/jobs", tags=["岗位"])


@router.get("")
async def list_jobs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    keyword: str | None = Query(None, max_length=200),
    status: Literal["active", "disabled"] | None = None,
):
    return await jobs.list_jobs(
        request.app.state.mysql, page, page_size, keyword, status
    )


@router.post("", status_code=201)
async def create(request: Request, data: JobCreate):
    return await jobs.create_job(request.app.state.mysql, data)


@router.get("/{job_id}")
async def detail(request: Request, job_id: int):
    return await jobs.detail(request.app.state.mysql, job_id)


@router.patch("/{job_id}")
async def patch(request: Request, job_id: int, data: JobPatch):
    return await jobs.patch_job(request.app.state.mysql, job_id, data)


@router.post("/{job_id}/publish")
async def publish(request: Request, job_id: int, data: PublishRequest):
    return await jobs.publish(request.app.state.mysql, job_id, data)


@router.post("/{job_id}/disable")
async def disable(request: Request, job_id: int):
    return await jobs.disable(request.app.state.mysql, job_id)


@router.post("/{job_id}/enable")
async def enable(request: Request, job_id: int):
    return await jobs.enable(request.app.state.mysql, job_id)


@router.delete("/{job_id}", status_code=204)
async def delete_job(request: Request, job_id: int):
    await jobs.delete_job(request.app.state.mysql, job_id)
    return Response(status_code=204)
