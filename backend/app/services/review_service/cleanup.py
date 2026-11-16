import asyncio
from contextlib import AsyncExitStack

from sqlalchemy import select

from app.core.errors import BusinessError
from app.models.mysql.entities import Candidate, Event, Reservation
from app.repositories.common import require
from app.repositories.evaluation_repo.visibility import DELETED_EVENT, is_deleted


async def remove_evaluations(db, runtime, candidate_ids):
    ids = sorted(set(candidate_ids))
    async with AsyncExitStack() as stack:
        for cid in ids:
            lock = runtime.locks.setdefault(cid, asyncio.Lock())
            if lock.locked():
                raise BusinessError("部分记录仍在处理中，请稍后重试", 409)
            await stack.enter_async_context(lock)
        removed, already = [], []
        async with db.session() as session:
            for cid in ids:
                candidate = await require(session, Candidate, cid, lock=True)
                if await is_deleted(session, cid):
                    already.append(str(cid))
                    continue
                if candidate.processing_status not in (
                    "failed",
                    "completed",
                    "waiting_review",
                ):
                    raise BusinessError("运行中的评估不能删除", 409)
                reserved = await session.scalar(
                    select(Reservation.id).where(Reservation.candidate_id == cid)
                )
                if candidate.review_status == "approved" or reserved:
                    raise BusinessError(
                        "已准入面试或已预约的记录不能作为无效数据删除", 409
                    )
                session.add(
                    Event(
                        batch_id=candidate.batch_id,
                        candidate_id=cid,
                        event_type=DELETED_EVENT,
                        message="用户删除无效评估记录；原件、结果与历史日志保留",
                    )
                )
                removed.append(str(cid))
        return {"deleted": removed, "already_deleted": already}
