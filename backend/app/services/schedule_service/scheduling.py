import asyncio
from datetime import UTC, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.core.errors import BusinessError
from app.models.mysql.entities import Batch, Candidate, Reservation, Slot
from app.repositories.common import require, serialize

# Single-process runtime enforces a database advisory lock; serialize calendar writes too.
calendar_lock = asyncio.Lock()


def slot_values(data):
    try:
        ZoneInfo(data.timezone)
    except ZoneInfoNotFoundError:
        raise BusinessError("无效 IANA 时区") from None
    start = data.starts_at.astimezone(UTC).replace(tzinfo=None)
    end = data.ends_at.astimezone(UTC).replace(tzinfo=None)
    if end - start != timedelta(minutes=45):
        raise BusinessError("每个面试时段必须为 45 分钟")
    return {
        "starts_at": start,
        "ends_at": end,
        "timezone": data.timezone,
        "interviewer": data.interviewer,
    }


async def save_slot(db, batch_id, data, slot_id=None):
    values = slot_values(data)
    async with calendar_lock, db.session() as session:
        await require(session, Batch, batch_id, lock=True)
        rows = (
            await session.scalars(
                select(Slot).where(Slot.batch_id == batch_id).with_for_update()
            )
        ).all()
        if slot_id is None and len(rows) >= 4:
            raise BusinessError("每个批次最多配置四个时段")
        if any(
            r.id != slot_id
            and r.starts_at < values["ends_at"]
            and r.ends_at > values["starts_at"]
            for r in rows
        ):
            raise BusinessError("时段重叠", 409)
        if slot_id:
            slot = await require(session, Slot, slot_id, lock=True)
            occupied = await session.scalar(
                select(Reservation.id).where(Reservation.slot_id == slot_id)
            )
            if occupied or slot.batch_id != batch_id:
                raise BusinessError("已预约时段不能修改", 409)
            for key, value in values.items():
                setattr(slot, key, value)
        else:
            slot = Slot(batch_id=batch_id, **values)
            session.add(slot)
        await session.flush()
        return serialize(slot)


async def delete_slot(db, slot_id):
    async with calendar_lock, db.session() as session:
        slot = await require(session, Slot, slot_id, lock=True)
        if await session.scalar(
            select(Reservation.id).where(Reservation.slot_id == slot_id)
        ):
            raise BusinessError("已预约时段不能删除", 409)
        await session.delete(slot)


async def list_slots(db, batch_id):
    async with db.session() as session:
        await require(session, Batch, batch_id)
        return [
            serialize(r)
            for r in (
                await session.scalars(
                    select(Slot)
                    .where(Slot.batch_id == batch_id)
                    .order_by(Slot.starts_at)
                )
            ).all()
        ]


def ranking_key(candidate, fields):
    scores = {r["dimension_id"]: r["score"] for r in candidate.dimension_scores or []}
    return tuple(
        -float(candidate.total_score if f == "total_score" else scores.get(f, 0))
        for f in fields
    ) + (candidate.id,)


async def schedule(db, batch_id):
    async with calendar_lock, db.session() as session:
        batch = await require(session, Batch, batch_id, lock=True)
        if batch.status != "evaluation_done":
            raise BusinessError("批次仍有未完成评估", 409)
        slots = (
            await session.scalars(
                select(Slot)
                .where(Slot.batch_id == batch_id)
                .order_by(Slot.starts_at)
                .with_for_update()
            )
        ).all()
        if len(slots) != 4:
            raise BusinessError("请先配置四个实际时段", 409)
        rows = (
            await session.scalars(
                select(Candidate)
                .where(
                    Candidate.batch_id == batch_id,
                    Candidate.review_status == "approved",
                    Candidate.processing_status == "completed",
                    Candidate.total_score.is_not(None),
                )
                .with_for_update()
            )
        ).all()
        existing = (await session.scalars(select(Reservation))).all()
        occupied_ids = {r.slot_id for r in existing}
        reserved_candidates = {r.candidate_id for r in existing}
        all_slots = {r.id: r for r in (await session.scalars(select(Slot))).all()}
        fields = [s["field"] for s in batch.rule_snapshot["sort_priority"]]
        for candidate in sorted(rows, key=lambda c: ranking_key(c, fields)):
            if candidate.id in reserved_candidates:
                continue
            selected = None
            for slot in slots:
                if slot.id in occupied_ids:
                    continue
                conflict = any(
                    (slot.interviewer or "default")
                    == (all_slots[r.slot_id].interviewer or "default")
                    and slot.starts_at < all_slots[r.slot_id].ends_at
                    and slot.ends_at > all_slots[r.slot_id].starts_at
                    for r in existing
                )
                if not conflict:
                    selected = slot
                    break
            if selected is None:
                candidate.schedule_status, candidate.waitlist_reason = (
                    "waitlisted",
                    "时段已满或面试官时间冲突",
                )
                continue
            reservation = Reservation(
                batch_id=batch_id,
                candidate_id=candidate.id,
                slot_id=selected.id,
                priority_snapshot={
                    "fields": fields,
                    "key": list(ranking_key(candidate, fields)),
                },
            )
            session.add(reservation)
            existing.append(reservation)
            occupied_ids.add(selected.id)
            candidate.schedule_status, candidate.waitlist_reason = "scheduled", None
    return await schedule_detail(db, batch_id)


async def schedule_detail(db, batch_id):
    async with db.session() as session:
        await require(session, Batch, batch_id)
        reservations = (
            await session.scalars(
                select(Reservation).where(Reservation.batch_id == batch_id)
            )
        ).all()
        waitlist = (
            await session.scalars(
                select(Candidate).where(
                    Candidate.batch_id == batch_id,
                    Candidate.schedule_status == "waitlisted",
                )
            )
        ).all()
        return {
            "reservations": [serialize(r) for r in reservations],
            "waitlist": [serialize(c) for c in waitlist],
        }
