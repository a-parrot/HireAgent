"""Admission to interview scheduling; no meeting or notification is sent here."""

from app.core.errors import BusinessError
from app.models.mysql.entities import Candidate, Event, Review
from app.repositories.common import require
from app.repositories.evaluation_repo.visibility import ensure_visible


async def approve(db, candidate_id):
    async with db.session() as session:
        candidate = await require(session, Candidate, candidate_id, lock=True)
        await ensure_visible(session, candidate_id)
        if candidate.review_status == "approved":
            return
        if candidate.recommendation != "recommended" or candidate.needs_human_review:
            raise BusinessError("候选人需要复核，不能自动进入面试", 409)
        if candidate.review_status != "pending":
            raise BusinessError("候选人已有人工决定，不能自动覆盖", 409)
        candidate.review_status = "approved"
        candidate.review_version += 1
        session.add(
            Review(
                candidate_id=candidate_id,
                operation="approve",
                review_version=candidate.review_version,
                operator_name="系统自动分流",
                reason="达到岗位推荐分数，硬条件满足且证据完整，自动进入面试候选队列",
                supplements=[],
                resume_status="not_required",
            )
        )
        session.add(
            Event(
                batch_id=candidate.batch_id,
                candidate_id=candidate_id,
                node_name="auto_approve",
                event_type="auto_approved",
                message="评分达标，自动进入面试候选队列",
            )
        )


async def run(runtime, state):
    await approve(runtime.db, state["candidate_id"])
    return {"decision": "approve"}
