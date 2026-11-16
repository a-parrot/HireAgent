import asyncio
from datetime import UTC, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.errors import BusinessError
from app.models.mysql.entities import (
    Batch,
    Candidate,
    Event,
    Job,
    Reservation,
    Slot,
    utcnow,
)
from app.repositories.common import require, serialize
from app.repositories.evaluation_repo.visibility import visible_candidates
from sqlalchemy import case, func, or_, select

# Single-process runtime enforces a database advisory lock; serialize calendar writes too.
calendar_lock = asyncio.Lock()


def slot_values(data):
    try:
        ZoneInfo(data.timezone)
    except ZoneInfoNotFoundError:
        raise BusinessError("无效 IANA 时区") from None
    start = data.starts_at.astimezone(UTC).replace(tzinfo=None)
    end = data.ends_at.astimezone(UTC).replace(tzinfo=None)
    if end <= start:
        raise BusinessError("结束时间须晚于开始时间")
    return {
        "starts_at": start,
        "ends_at": end,
        "timezone": data.timezone,
        "interviewer": (data.interviewer or "").strip() or None,
    }


async def save_slot(db, batch_id, data, slot_id=None):
    values = slot_values(data)
    async with calendar_lock, db.session() as session:
        await require(session, Batch, batch_id, lock=True)
        rows = (
            await session.scalars(
                select(Slot)
                .where(
                    func.coalesce(func.nullif(Slot.interviewer, ""), "default")
                    == (values["interviewer"] or "default")
                )
                .with_for_update()
            )
        ).all()
        if any(
            r.id != slot_id
            and r.starts_at < values["ends_at"]
            and r.ends_at > values["starts_at"]
            for r in rows
        ):
            raise BusinessError("面试官时段重叠", 409)
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
    return (
        (candidate.total_score is None,)
        + tuple(
            -float(
                (candidate.total_score or 0) if f == "total_score" else scores.get(f, 0)
            )
            for f in fields
        )
        + (candidate.id,)
    )


async def schedule(db, batch_id, *, automatic=False, candidate_ids=None):
    async with calendar_lock, db.session() as session:
        batch = await require(session, Batch, batch_id, lock=True)
        if batch.status != "evaluation_done" and not (
            automatic and candidate_ids is not None
        ):
            raise BusinessError("批次仍有未完成评估", 409)
        slots = (
            await session.scalars(
                select(Slot)
                .where(
                    Slot.batch_id == batch_id,
                    Slot.starts_at > utcnow() if automatic else True,
                )
                .order_by(Slot.starts_at)
                .with_for_update()
            )
        ).all()
        if not automatic and not slots:
            raise BusinessError("请先配置实际可用时段", 409)
        rows = (
            await session.scalars(
                select(Candidate)
                .where(
                    Candidate.batch_id == batch_id,
                    Candidate.review_status == "approved",
                    visible_candidates(),
                    Candidate.id.in_(candidate_ids)
                    if candidate_ids is not None
                    else True,
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
                    "尚未配置未来可用面试时段"
                    if not slots
                    else "时段已满或面试官时间冲突",
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


async def list_interview_records(db, page=1, page_size=20):
    eligible = select(Candidate.batch_id).where(
        Candidate.review_status == "approved",
        visible_candidates(),
    )
    query = (
        select(Batch, Job.name)
        .select_from(Batch)
        .join(Job, Job.id == Batch.job_id)
        .where(or_(Batch.id.in_(eligible), Batch.id.in_(select(Reservation.batch_id))))
    )
    async with db.session() as session:
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        rows = (
            await session.execute(
                query.order_by(Batch.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        ids = [batch.id for batch, _ in rows]
        counts = (
            (
                await session.execute(
                    select(
                        Candidate.batch_id,
                        func.count(),
                        func.sum(
                            case((Candidate.schedule_status == "scheduled", 1), else_=0)
                        ),
                    )
                    .where(
                        Candidate.batch_id.in_(ids),
                        Candidate.review_status == "approved",
                        visible_candidates(),
                    )
                    .group_by(Candidate.batch_id)
                )
            ).all()
            if ids
            else []
        )
        stats = {bid: (count, int(scheduled or 0)) for bid, count, scheduled in counts}
        return {
            "items": [
                {
                    **serialize(batch),
                    "job_name": name,
                    "interview_count": stats.get(batch.id, (0, 0))[0],
                    "scheduled_count": stats.get(batch.id, (0, 0))[1],
                }
                for batch, name in rows
            ],
            "total": total,
        }


def generated_settings(starts_at, timezone, interviewer):
    from app.schemas.business import SlotInput

    if starts_at.tzinfo is None:
        raise BusinessError("起始时间必须带时区")
    values = slot_values(
        SlotInput(
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=45),
            timezone=timezone,
            interviewer=(interviewer or "").strip() or None,
        )
    )
    if values["starts_at"] <= utcnow():
        raise BusinessError("起始时间必须晚于当前时间")
    return values


async def generate_schedule(db, candidate_ids, settings):
    """Atomically allocate consecutive 45-minute slots, keeping previous appointments."""
    if not candidate_ids:
        return {"created_slots": 0, "new_reservations": 0}
    async with calendar_lock, db.session() as session:
        batch_ids = list(
            await session.scalars(
                select(Candidate.batch_id)
                .where(Candidate.id.in_(candidate_ids))
                .distinct()
            )
        )
        batches = (
            await session.scalars(
                select(Batch)
                .where(Batch.id.in_(batch_ids))
                .order_by(Batch.id)
                .with_for_update()
            )
        ).all()
        rows = (
            await session.scalars(
                select(Candidate)
                .where(
                    Candidate.id.in_(candidate_ids),
                    Candidate.review_status == "approved",
                    visible_candidates(),
                )
                .with_for_update()
            )
        ).all()
        slots = list((await session.scalars(select(Slot))).all())
        existing = (await session.scalars(select(Reservation))).all()
        occupied = {r.slot_id for r in existing}
        reserved = {r.candidate_id for r in existing}
        fields = {
            b.id: [entry["field"] for entry in b.rule_snapshot["sort_priority"]]
            for b in batches
        }
        ordered = sorted(
            rows,
            key=lambda c: (
                c.total_score is None,
                -float(c.total_score or 0),
                ranking_key(c, fields[c.batch_id]),
            ),
        )
        cursor, created, added = settings["starts_at"], 0, 0
        interviewer = settings["interviewer"]
        for candidate in ordered:
            if candidate.id in reserved:
                candidate.schedule_status, candidate.waitlist_reason = "scheduled", None
                continue
            while True:
                end = cursor + timedelta(minutes=45)
                overlap = [s for s in slots if s.starts_at < end and s.ends_at > cursor]
                reusable = next(
                    (
                        s
                        for s in overlap
                        if s.batch_id == candidate.batch_id
                        and s.id not in occupied
                        and s.starts_at == cursor
                        and s.ends_at == end
                        and (s.interviewer or "default") == (interviewer or "default")
                    ),
                    None,
                )
                conflicts = [
                    s
                    for s in overlap
                    if (s.batch_id == candidate.batch_id and s is not reusable)
                    or (
                        s.id in occupied
                        and (s.interviewer or "default") == (interviewer or "default")
                    )
                ]
                if conflicts:
                    cursor = max(s.ends_at for s in conflicts)
                    continue
                selected = reusable
                if selected is None:
                    selected = Slot(
                        batch_id=candidate.batch_id,
                        starts_at=cursor,
                        ends_at=end,
                        timezone=settings["timezone"],
                        interviewer=interviewer,
                    )
                    session.add(selected)
                    await session.flush()
                    slots.append(selected)
                    created += 1
                session.add(
                    Reservation(
                        batch_id=candidate.batch_id,
                        candidate_id=candidate.id,
                        slot_id=selected.id,
                        priority_snapshot={
                            "fields": fields[candidate.batch_id],
                            "key": list(
                                ranking_key(candidate, fields[candidate.batch_id])
                            ),
                        },
                    )
                )
                session.add(
                    Event(
                        batch_id=candidate.batch_id,
                        candidate_id=candidate.id,
                        node_name="auto_schedule",
                        event_type="auto_scheduled",
                        message="按指定起始时间自动生成面试预约",
                        details={
                            "starts_at": cursor.isoformat() + "Z",
                            "ends_at": end.isoformat() + "Z",
                            "interviewer": interviewer,
                            "timezone": settings["timezone"],
                            "duration_minutes": 45,
                        },
                    )
                )
                candidate.schedule_status, candidate.waitlist_reason = "scheduled", None
                occupied.add(selected.id)
                reserved.add(candidate.id)
                added += 1
                cursor = end
                break
        return {"created_slots": created, "new_reservations": added}
