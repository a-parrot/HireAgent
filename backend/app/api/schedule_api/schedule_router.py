from fastapi import APIRouter, Query, Request, Response

from app.agents.interview_agent.nodes.schedule_ready import schedule_ready
from app.api.authorization import operator_data
from app.models.mysql.entities import Slot
from app.repositories.common import require
from app.schemas.business import (
    ActionApproval,
    InterviewBooking,
    InterviewReschedule,
    PreviewInput,
    SlotInput,
)
from app.services.schedule_service import interviews, scheduling

router = APIRouter(prefix="/api", tags=["排期与外部动作"])


@router.get("/interviews")
async def interview_list(
    request: Request,
    keyword: str | None = None,
    candidate_id: int | None = Query(None, ge=1),
    status: str | None = Query(None, pattern="^(pending|scheduled)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return await interviews.list_interviews(
        request.app.state.mysql,
        keyword=keyword,
        candidate_id=candidate_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post("/interviews", status_code=201)
async def book_interviews(request: Request, data: InterviewBooking):
    return await interviews.book(request.app.state.mysql, data)


@router.patch("/interviews/{reservation_id}")
async def reschedule_interview(
    request: Request, reservation_id: int, data: InterviewReschedule
):
    return await interviews.reschedule(request.app.state.mysql, reservation_id, data)


@router.delete("/interviews/{reservation_id}")
async def cancel_interview(
    request: Request, reservation_id: int, preview_version: int = Query(..., ge=0)
):
    return await interviews.cancel(
        request.app.state.mysql, reservation_id, preview_version
    )


@router.get("/batches/{batch_id}/slots")
async def slots(request: Request, batch_id: int):
    return await scheduling.list_slots(request.app.state.mysql, batch_id)


@router.post("/batches/{batch_id}/slots", status_code=201)
async def create_slot(request: Request, batch_id: int, data: SlotInput):
    slot = await scheduling.save_slot(request.app.state.mysql, batch_id, data)
    await schedule_ready(request.app.state.mysql, batch_id)
    return slot


@router.patch("/slots/{slot_id}")
async def edit_slot(request: Request, slot_id: int, data: SlotInput):
    async with request.app.state.mysql.session() as session:
        slot = await require(session, Slot, slot_id)
        batch_id = slot.batch_id
    result = await scheduling.save_slot(
        request.app.state.mysql, batch_id, data, slot_id
    )
    await schedule_ready(request.app.state.mysql, batch_id)
    return result


@router.delete("/slots/{slot_id}", status_code=204)
async def delete_slot(request: Request, slot_id: int):
    await scheduling.delete_slot(request.app.state.mysql, slot_id)
    return Response(status_code=204)


@router.post("/batches/{batch_id}/schedule")
async def schedule(request: Request, batch_id: int):
    return await scheduling.schedule(request.app.state.mysql, batch_id)


@router.get("/batches/{batch_id}/schedule")
async def detail(request: Request, batch_id: int):
    return await scheduling.schedule_detail(request.app.state.mysql, batch_id)


@router.get("/reservations/{reservation_id}/action-preview")
async def preview(request: Request, reservation_id: int):
    return await request.app.state.actions.preview(reservation_id)


@router.put("/reservations/{reservation_id}/action-preview")
async def edit_preview(request: Request, reservation_id: int, data: PreviewInput):
    return await request.app.state.actions.edit_preview(reservation_id, data)


@router.post("/reservations/{reservation_id}/approve-actions")
async def approve(request: Request, reservation_id: int, data: ActionApproval):
    data = operator_data(request, data)
    return await request.app.state.actions.approve(reservation_id, data)


@router.post("/reservations/{reservation_id}/retry-actions")
async def retry(request: Request, reservation_id: int):
    return await request.app.state.actions.execute(reservation_id)


@router.post("/reservations/{reservation_id}/reconcile-actions")
async def reconcile(request: Request, reservation_id: int):
    return await request.app.state.actions.reconcile(reservation_id)


@router.get("/scheduling-records")
async def scheduling_records(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    return await scheduling.list_interview_records(
        request.app.state.mysql, page, page_size
    )
