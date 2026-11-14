from typing import Annotated, Literal

from fastapi import APIRouter, Form, Query, Request, Response, UploadFile
from fastapi import File as UploadParam
from pydantic import BaseModel, Field

from app.services.resume_service import workspace
from app.services.workflow_service import operations

router = APIRouter(prefix="/api", tags=["岗位简历"])


@router.get("/resume-workspace/jobs")
async def jobs(request: Request):
    return await workspace.job_summary(request.app.state.mysql)


@router.get("/jobs/{job_id}/resumes")
async def resumes(
    request: Request,
    job_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = Query(None, max_length=255),
    status: Literal["pending", "running", "completed", "failed"] | None = None,
):
    return await workspace.list_resumes(
        request.app.state.mysql, job_id, page, page_size, keyword, status
    )


@router.post("/jobs/{job_id}/resumes", status_code=201)
async def upload(
    request: Request,
    job_id: int,
    files: Annotated[list[UploadFile], UploadParam()],
    sha256s: Annotated[list[str] | None, Form()] = None,
):
    result, tasks = await workspace.upload_many(
        request.app.state.mysql, request.app.state.settings, job_id, files, sha256s
    )
    request.app.state.import_runtime.submit(tasks)
    return result


@router.get("/jobs/{job_id}/resumes/{resume_id}")
async def detail(request: Request, job_id: int, resume_id: int):
    return await workspace.detail(
        request.app.state.mysql, request.app.state.settings, job_id, resume_id
    )


@router.delete("/jobs/{job_id}/resumes/{resume_id}", status_code=204)
async def remove(request: Request, job_id: int, resume_id: int):
    await workspace.remove(request.app.state.mysql, job_id, resume_id)
    return Response(status_code=204)


@router.post("/jobs/{job_id}/resumes/{resume_id}/retry", status_code=202)
async def retry(request: Request, job_id: int, resume_id: int):
    tid = await workspace.retry(request.app.state.mysql, job_id, resume_id)
    request.app.state.import_runtime.submit([tid])
    return {"task_id": str(tid), "status": "pending"}


class StartEvaluationInput(BaseModel):
    resume_ids: list[int] = Field(min_length=1, max_length=1000)
    rule_version_id: int = Field(gt=0)
    request_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/jobs/{job_id}/evaluate", status_code=202)
async def start_evaluation(request: Request, job_id: int, body: StartEvaluationInput):
    record = await workspace.create_evaluation(
        request.app.state.mysql,
        job_id,
        body.resume_ids,
        body.rule_version_id,
        config=request.app.state.settings,
        evaluation_key=body.request_id,
    )
    result = await operations.start_batch(
        request.app.state.mysql, request.app.state.runtime, int(record["id"])
    )
    return {
        "status": result["status"],
        "already_started": result["already_started"],
        "accepted": record["imported_count"],
    }
