from typing import Literal

from fastapi import APIRouter, Query, Request, Response

from app.models.mysql.entities import Candidate
from app.repositories.common import require
from app.services.workflow_service import operations

router = APIRouter(prefix="/api", tags=["工作流"])


@router.get("/candidates/{candidate_id}/export")
async def export_candidate(
    request: Request, candidate_id: int, format: Literal["json", "csv"] = "json"
):
    async with request.app.state.mysql.session() as session:
        candidate = await require(session, Candidate, candidate_id)
        batch_id = candidate.batch_id
    data, media_type = await operations.export(
        request.app.state.mysql, batch_id, format, candidate_id=candidate_id
    )
    return Response(
        data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="candidate-{candidate_id}.{format}"'
        },
    )


@router.post("/batches/{batch_id}/run", status_code=202)
async def run(request: Request, batch_id: int):
    return await operations.start_batch(
        request.app.state.mysql, request.app.state.runtime, batch_id
    )


@router.post("/candidates/{candidate_id}/retry", status_code=202)
async def retry(request: Request, candidate_id: int):
    return await operations.retry(
        request.app.state.mysql, request.app.state.runtime, candidate_id
    )


@router.get("/batches/{batch_id}/events")
async def events(
    request: Request,
    batch_id: int,
    after_id: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    return await operations.events(request.app.state.mysql, batch_id, after_id, limit)


@router.get("/batches/{batch_id}/export")
async def export(
    request: Request, batch_id: int, format: Literal["json", "csv"] = "json"
):
    data, media_type = await operations.export(
        request.app.state.mysql, batch_id, format
    )
    return Response(
        data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="batch-{batch_id}.{format}"'
        },
    )
