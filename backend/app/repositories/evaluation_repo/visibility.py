"""Soft removal preserves evaluation data, checkpoints and audit logs."""

from sqlalchemy import select

from app.core.errors import BusinessError
from app.models.mysql.entities import Candidate, Event

DELETED_EVENT = "evaluation_deleted"


def visible_candidates():
    ids = (
        select(Event.candidate_id)
        .where(Event.event_type == DELETED_EVENT, Event.candidate_id.is_not(None))
        .correlate(None)
    )
    return Candidate.id.not_in(ids)


async def is_deleted(session, candidate_id):
    return (
        await session.scalar(
            select(Event.id)
            .where(
                Event.candidate_id == candidate_id, Event.event_type == DELETED_EVENT
            )
            .limit(1)
        )
        is not None
    )


async def ensure_visible(session, candidate_id):
    if await is_deleted(session, candidate_id):
        raise BusinessError("评估记录已删除，历史日志仍可查询", 410)
