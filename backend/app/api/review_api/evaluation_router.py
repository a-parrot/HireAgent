from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field, field_validator

from app.agents.interview_agent.nodes.auto_schedule import run as auto_schedule
from app.core.errors import BusinessError
from app.services.review_service.cleanup import remove_evaluations
from app.services.review_service.evaluations import list_results

router = APIRouter(prefix="/api/evaluations", tags=["评估管理"])


@router.get("")
async def results(
    request: Request,
    job_id: int | None = Query(None, gt=0),
    keyword: str | None = Query(None, max_length=255),
    bucket: Literal["high", "middle", "low", "unscored"] | None = None,
    min_score: float | None = Query(None, ge=0, le=100),
    max_score: float | None = Query(None, ge=0, le=100),
    workflow: Literal[
        "waiting_review",
        "approved",
        "scheduled",
        "waitlisted",
        "awaiting_schedule",
        "deferred",
    ]
    | None = None,
    latest_only: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    if min_score is not None and max_score is not None and min_score > max_score:
        raise BusinessError("最低分不能大于最高分")
    return await list_results(
        request.app.state.mysql,
        job_id=job_id,
        keyword=keyword,
        bucket=bucket,
        min_score=min_score,
        max_score=max_score,
        workflow=workflow,
        latest_only=latest_only,
        page=page,
        page_size=page_size,
    )


class DeleteEvaluationsInput(BaseModel):
    candidate_ids: list[int] = Field(min_length=1, max_length=1000)


@router.post("/delete")
async def remove_many(request: Request, body: DeleteEvaluationsInput):
    return await remove_evaluations(
        request.app.state.mysql, request.app.state.runtime, body.candidate_ids
    )


@router.delete("/{candidate_id}")
async def remove_one(request: Request, candidate_id: int):
    return await remove_evaluations(
        request.app.state.mysql, request.app.state.runtime, [candidate_id]
    )


class AutoScheduleInput(BaseModel):
    job_id: int | None = Field(default=None, gt=0)
    candidate_ids: list[int] | None = Field(default=None, min_length=1, max_length=1000)
    starts_at: datetime | None = None
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
    interviewer: str | None = Field(default=None, max_length=128)

    @field_validator("starts_at")
    @classmethod
    def aware_start(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("起始时间必须带时区")
        return value


@router.post("/auto-schedule")
async def schedule_high_scores(request: Request, body: AutoScheduleInput):
    return await auto_schedule(request.app.state.runtime, body.model_dump())
