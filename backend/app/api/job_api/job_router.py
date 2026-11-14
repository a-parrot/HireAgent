from fastapi import APIRouter, Query, Request

from app.schemas.business import JobCreate, JobPatch, PublishRequest
from app.services.job_service import jobs

router = APIRouter(prefix="/api/jobs", tags=["岗位"])


@router.get("")
async def list_jobs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    return await jobs.list_jobs(request.app.state.mysql, page, page_size)


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
