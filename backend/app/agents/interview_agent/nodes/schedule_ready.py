"""Admission to interview scheduling; no meeting or notification is sent here."""

from sqlalchemy import select

from app.core.logging import traced
from app.models.mysql.entities import Batch, Candidate
from app.repositories.common import require
from app.repositories.evaluation_repo.visibility import visible_candidates
from app.services.schedule_service import scheduling


@traced("interview.schedule_ready", agent="interview", id_arg="batch_id")
async def schedule_ready(db, batch_id):
    async with db.session() as session:
        batch = await require(session, Batch, batch_id)
        if batch.status != "evaluation_done":
            return
        eligible = await session.scalar(
            select(Candidate.id)
            .where(
                Candidate.batch_id == batch_id,
                Candidate.review_status == "approved",
                Candidate.processing_status == "completed",
                visible_candidates(),
            )
            .limit(1)
        )
    if eligible is not None:
        await scheduling.schedule(db, batch_id, automatic=True)
