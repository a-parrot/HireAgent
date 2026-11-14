from fastapi import APIRouter, Request, Response

from app.models.mysql.entities import Slot
from app.repositories.common import require
from app.schemas.business import ActionApproval, PreviewInput, SlotInput
from app.services.schedule_service import scheduling

router = APIRouter(prefix="/api", tags=["排期与外部动作"])


@router.get("/batches/{batch_id}/slots")
async def slots(request: Request, batch_id: int):
    return await scheduling.list_slots(request.app.state.mysql, batch_id)


@router.post("/batches/{batch_id}/slots", status_code=201)
async def create_slot(request: Request, batch_id: int, data: SlotInput):
    return await scheduling.save_slot(request.app.state.mysql, batch_id, data)


@router.patch("/slots/{slot_id}")
async def edit_slot(request: Request, slot_id: int, data: SlotInput):
    async with request.app.state.mysql.session() as session:
        slot = await require(session, Slot, slot_id)
        batch_id = slot.batch_id
    return await scheduling.save_slot(request.app.state.mysql, batch_id, data, slot_id)


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
    return await request.app.state.actions.approve(reservation_id, data)


@router.post("/reservations/{reservation_id}/retry-actions")
async def retry(request: Request, reservation_id: int):
    return await request.app.state.actions.execute(reservation_id)


@router.post("/reservations/{reservation_id}/reconcile-actions")
async def reconcile(request: Request, reservation_id: int):
    return await request.app.state.actions.reconcile(reservation_id)
