from typing import Annotated, Literal

from fastapi import APIRouter, Form, Query, Request, Response, UploadFile
from fastapi import File as UploadParam
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.errors import BusinessError
from app.models.mysql.entities import Batch, Event, JobRuleVersion
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
    evaluation_status: Literal[
        "queued", "pending", "running", "completed", "failed", "waiting_review", "none"
    ]
    | None = None,
):
    return await workspace.list_resumes(
        request.app.state.mysql,
        job_id,
        page,
        page_size,
        keyword,
        status,
        evaluation_status,
    )


@router.post("/jobs/{job_id}/resumes", status_code=201)
async def upload(
    request: Request,
    job_id: int,
    files: Annotated[list[UploadFile], UploadParam()],
    sha256s: Annotated[list[str] | None, Form()] = None,
    auto_evaluate: Annotated[bool, Form()] = False,
    rule_version_id: Annotated[int | None, Form(gt=0)] = None,
    request_id: Annotated[
        str | None, Form(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    ] = None,
):
    if auto_evaluate:
        if rule_version_id is None or request_id is None:
            raise BusinessError("解析并评估需要已发布规则版本和请求标识")
        async with request.app.state.mysql.session() as session:
            version = await session.get(JobRuleVersion, rule_version_id)
            if version is None or version.job_id != job_id:
                raise BusinessError("请先发布当前岗位的评分规则")
    result, tasks = await workspace.upload_many(
        request.app.state.mysql, request.app.state.settings, job_id, files, sha256s
    )
    request.app.state.import_runtime.submit(tasks)
    if auto_evaluate:
        # On a lost response the same request can safely reuse its previously committed evaluation.
        async with request.app.state.mysql.session() as session:
            repeated = await session.scalar(
                select(Batch.id)
                .join(Event)
                .where(
                    Batch.job_id == job_id,
                    Event.event_type == "evaluation_request",
                    Event.message == request_id,
                )
            )
            file_ids = [
                int(item["file_id"])
                for item in result["items"]
                if item["result"] != "rejected"
            ]
            latest = await workspace.latest_evaluations(session, job_id, file_ids)
        ids = list(
            dict.fromkeys(
                int(item["resume_id"])
                for item in result["items"]
                if item["result"] != "rejected"
                and (
                    repeated
                    or item["result"] == "accepted"
                    or int(item["file_id"]) not in latest
                )
            )
        )
        if ids:
            record = await workspace.create_evaluation(
                request.app.state.mysql,
                job_id,
                ids,
                rule_version_id,
                config=request.app.state.settings,
                evaluation_key=request_id,
                allow_unparsed=True,
            )
            result["evaluation"] = await operations.start_batch(
                request.app.state.mysql,
                request.app.state.runtime,
                int(record["id"]),
            )
    return result


@router.get("/jobs/{job_id}/resumes/{resume_id}")
async def detail(request: Request, job_id: int, resume_id: int):
    return await workspace.detail(
        request.app.state.mysql, request.app.state.settings, job_id, resume_id
    )


@router.delete("/jobs/{job_id}/resumes/{resume_id}", status_code=204)
async def remove(request: Request, job_id: int, resume_id: int):
    await workspace.remove(
        request.app.state.mysql,
        job_id,
        resume_id,
        getattr(request.app.state, "runtime", None),
    )
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
        allow_unparsed=True,
    )
    result = await operations.start_batch(
        request.app.state.mysql, request.app.state.runtime, int(record["id"])
    )
    return {
        "status": result["status"],
        "already_started": result["already_started"],
        "accepted": record["imported_count"],
    }
