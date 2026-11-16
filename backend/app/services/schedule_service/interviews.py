"""Candidate-oriented interview booking, with atomic calendar conflict checks."""

from datetime import timedelta

from app.core.errors import BusinessError
from app.core.logging import logger, traced
from app.models.mysql.entities import (
    ActionRecord,
    Batch,
    Candidate,
    Event,
    Job,
    Reservation,
    Slot,
    utcnow,
)
from app.repositories.common import require, serialize
from app.repositories.evaluation_repo.visibility import (
    ensure_visible,
    visible_candidates,
)
from app.services.schedule_service.scheduling import calendar_lock, slot_values
from sqlalchemy import func, or_, select


async def list_interviews(
    db, *, keyword=None, status=None, candidate_id=None, page=1, page_size=20
):
    query = (
        select(Candidate, Job.name, Reservation, Slot)
        .join(Batch, Batch.id == Candidate.batch_id)
        .join(Job, Job.id == Batch.job_id)
        .outerjoin(Reservation, Reservation.candidate_id == Candidate.id)
        .outerjoin(Slot, Slot.id == Reservation.slot_id)
        .where(
            visible_candidates(),
            or_(
                Reservation.id.is_not(None),
                Candidate.review_status == "approved",
            ),
        )
    )
    if candidate_id is not None:
        query = query.where(Candidate.id == candidate_id)
    if keyword:
        query = query.where(
            or_(
                Candidate.name.contains(keyword, autoescape=True),
                Candidate.original_filename.contains(keyword, autoescape=True),
                Job.name.contains(keyword, autoescape=True),
            )
        )
    async with db.session() as session:
        base = query.subquery()
        total_all = await session.scalar(select(func.count()).select_from(base))
        booked = await session.scalar(
            select(func.count()).select_from(
                query.where(Reservation.id.is_not(None)).subquery()
            )
        )
        if status == "scheduled":
            query = query.where(Reservation.id.is_not(None))
        elif status == "pending":
            query = query.where(Reservation.id.is_(None))
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        rows = (
            await session.execute(
                query.order_by(
                    Slot.starts_at.is_(None).desc(), Slot.starts_at, Candidate.id.desc()
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        ids = [r.id for _, _, r, _ in rows if r]
        protected = (
            set(
                (
                    await session.scalars(
                        select(ActionRecord.reservation_id).where(
                            ActionRecord.reservation_id.in_(ids),
                            or_(
                                ActionRecord.attempt_count > 0,
                                ActionRecord.status.in_(
                                    ["running", "succeeded", "uncertain"]
                                ),
                            ),
                        )
                    )
                ).all()
            )
            if ids
            else set()
        )
        return {
            "items": [
                {
                    "candidate": serialize(c),
                    "job_name": name,
                    "reservation": serialize(r) if r else None,
                    "slot": serialize(s) if s else None,
                    "editable": not r or r.id not in protected,
                }
                for c, name, r, s in rows
            ],
            "total": total,
            "counts": {
                "all": total_all,
                "scheduled": booked,
                "pending": total_all - booked,
            },
        }


async def check_conflict(session, start, end, interviewer, exclude=None):
    # Include free calendar slots too, so automatic scheduling cannot later create a conflict.
    query = select(Slot.id).where(
        Slot.starts_at < end,
        Slot.ends_at > start,
        func.coalesce(func.nullif(Slot.interviewer, ""), "default")
        == (interviewer or "default"),
    )
    if exclude is not None:
        query = query.where(Slot.id != exclude)
    if await session.scalar(query.limit(1)):
        raise BusinessError("面试官在该时间段已有安排，请调整时间或面试官", 409)


async def editable_reservation(session, reservation_id, version):
    reservation = await require(session, Reservation, reservation_id, lock=True)
    if reservation.preview_version != version:
        raise BusinessError("预约已变化，请刷新后重试", 409)
    actions = (
        await session.scalars(
            select(ActionRecord)
            .where(ActionRecord.reservation_id == reservation_id)
            .with_for_update()
        )
    ).all()
    if any(
        a.attempt_count or a.status in ("running", "succeeded", "uncertain")
        for a in actions
    ):
        raise BusinessError(
            "该预约已有会议或通知执行记录，请先核实外部平台，暂不能直接改期或取消", 409
        )
    return reservation, actions


@traced("interview.book", agent="interview")
async def book(db, data):
    start = slot_values(data)["starts_at"]
    duration = data.ends_at - data.starts_at
    if start <= utcnow():
        raise BusinessError("请选择未来的面试时间")
    ids = list(dict.fromkeys(data.candidate_ids))
    async with calendar_lock, db.session() as session:
        # All candidates and all slots succeed together; an error rolls back the whole request.
        result = []
        for index, cid in enumerate(ids):
            candidate = await require(session, Candidate, cid, lock=True)
            await ensure_visible(session, cid)
            if candidate.review_status != "approved":
                raise BusinessError("所选候选人尚未批准面试，请刷新列表", 409)
            if await session.scalar(
                select(Reservation.id).where(Reservation.candidate_id == cid)
            ):
                raise BusinessError("所选候选人已有预约，请使用改期", 409)
            current = start + index * (duration + timedelta(minutes=data.gap_minutes))
            end = current + duration
            interviewer = (data.interviewer or "").strip() or None
            await check_conflict(session, current, end, interviewer)
            slot = Slot(
                batch_id=candidate.batch_id,
                starts_at=current,
                ends_at=end,
                timezone=data.timezone,
                interviewer=interviewer,
            )
            session.add(slot)
            await session.flush()
            reservation = Reservation(
                batch_id=candidate.batch_id,
                candidate_id=cid,
                slot_id=slot.id,
                priority_snapshot={"source": "manual", "order": index},
            )
            session.add(reservation)
            candidate.schedule_status, candidate.waitlist_reason = "scheduled", None
            await session.flush()
            session.add(
                Event(
                    batch_id=candidate.batch_id,
                    candidate_id=cid,
                    event_type="interview_booked",
                    message="人工安排面试",
                    details={
                        "reservation_id": str(reservation.id),
                        "slot": serialize(slot),
                    },
                )
            )
            result.append(serialize(reservation))
        logger.bind(scheduled=len(result), candidate_ids=ids).info("interview.booked")
        return {"items": result, "scheduled": len(result)}


@traced("interview.reschedule", agent="interview", id_arg="reservation_id")
async def reschedule(db, reservation_id, data):
    values = slot_values(data)
    values["interviewer"] = (values["interviewer"] or "").strip() or None
    if values["starts_at"] <= utcnow():
        raise BusinessError("请选择未来的面试时间")
    async with calendar_lock, db.session() as session:
        reservation, _ = await editable_reservation(
            session, reservation_id, data.preview_version
        )
        slot = await require(session, Slot, reservation.slot_id, lock=True)
        before = serialize(slot)
        await check_conflict(
            session,
            values["starts_at"],
            values["ends_at"],
            values["interviewer"],
            slot.id,
        )
        for key, value in values.items():
            setattr(slot, key, value)
        reservation.preview_version += 1
        reservation.action_preview = reservation.approved_preview = None
        reservation.approved_preview_version = reservation.approved_by = (
            reservation.approved_at
        ) = None
        session.add(
            Event(
                batch_id=reservation.batch_id,
                candidate_id=reservation.candidate_id,
                event_type="interview_rescheduled",
                message="人工调整面试时间",
                details={"before": before, "after": serialize(slot)},
            )
        )
        await session.flush()
        return serialize(reservation)


@traced("interview.cancel", agent="interview", id_arg="reservation_id")
async def cancel(db, reservation_id, version):
    async with calendar_lock, db.session() as session:
        reservation, actions = await editable_reservation(
            session, reservation_id, version
        )
        candidate = await require(
            session, Candidate, reservation.candidate_id, lock=True
        )
        slot = await require(session, Slot, reservation.slot_id, lock=True)
        session.add(
            Event(
                batch_id=reservation.batch_id,
                candidate_id=candidate.id,
                event_type="interview_cancelled",
                message="人工取消面试预约",
                details={
                    "reservation": serialize(reservation),
                    "slot": serialize(slot),
                },
            )
        )
        for action in actions:
            await session.delete(action)
        await session.flush()
        await session.delete(reservation)
        await session.flush()
        # Remove the released slot so the background scheduler cannot rebook it.
        await session.delete(slot)
        candidate.schedule_status, candidate.waitlist_reason = "unscheduled", None
        return {"cancelled": str(reservation_id)}
