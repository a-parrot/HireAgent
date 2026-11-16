"""Schedule approved candidates, retaining evidence-complete automatic admission."""

import asyncio

from app.agents.interview_agent.nodes.auto_approve import approve
from app.core.logging import traced
from app.models.mysql.entities import Batch, Candidate, Job
from app.repositories.evaluation_repo.visibility import visible_candidates
from app.services.schedule_service import scheduling
from sqlalchemy import and_, func, or_, select


@traced("interview.auto_schedule", agent="interview", state_arg="state")
async def run(runtime, state):
    runtime.ensure_active()
    generation = (
        scheduling.generated_settings(
            state["starts_at"],
            state.get("timezone", "Asia/Shanghai"),
            state.get("interviewer"),
        )
        if state.get("starts_at")
        else None
    )
    recommend = func.coalesce(Batch.rule_snapshot["recommend_threshold"].as_float(), 75)
    latest = (
        select(func.max(Candidate.id))
        .join(Batch)
        .group_by(Batch.job_id, Candidate.file_id)
    )
    query = (
        select(Candidate.id, Candidate.batch_id, Candidate.review_status)
        .select_from(Candidate)
        .join(Batch, Batch.id == Candidate.batch_id)
        .join(Job, Job.id == Batch.job_id)
        .where(
            Candidate.id.in_(latest),
            visible_candidates(),
            or_(
                Candidate.review_status == "approved",
                and_(
                    Candidate.processing_status == "completed",
                    Candidate.total_score >= recommend,
                    Candidate.recommendation == "recommended",
                    Candidate.needs_human_review.is_(False),
                    Candidate.review_status == "pending",
                    Batch.status == "evaluation_done",
                ),
            ),
            Job.status == "active",
            Job.deleted_at.is_(None),
        )
    )
    if state.get("job_id"):
        query = query.where(Batch.job_id == state["job_id"])
    if state.get("candidate_ids") is not None:
        query = query.where(Candidate.id.in_(state["candidate_ids"]))
    async with runtime.db.session() as session:
        rows = (
            await session.execute(
                query.order_by(Candidate.total_score.desc(), Candidate.id)
            )
        ).all()
    batches, ids = {}, []
    for cid, bid, review_status in rows:
        runtime.ensure_active()
        # Manual approval is already durable. Do not wait for a queued workflow's
        # in-memory lock just to approve it again; scheduling rechecks under DB locks.
        if review_status != "approved":
            async with runtime.locks.setdefault(cid, asyncio.Lock()):
                await approve(runtime.db, cid)
        batches.setdefault(bid, []).append(cid)
        ids.append(cid)
    generated = {"created_slots": 0, "new_reservations": 0}
    if generation is not None:
        runtime.ensure_active()
        generated = await scheduling.generate_schedule(runtime.db, ids, generation)
    else:
        for bid, selected in batches.items():
            runtime.ensure_active()
            await scheduling.schedule(
                runtime.db, bid, automatic=True, candidate_ids=selected
            )
    async with runtime.db.session() as session:
        statuses = (
            (
                await session.execute(
                    select(
                        Candidate.id,
                        Candidate.schedule_status,
                        Candidate.waitlist_reason,
                    ).where(Candidate.id.in_(ids))
                )
            ).all()
            if ids
            else []
        )
    return {
        **generated,
        "eligible": len(ids),
        "scheduled": sum(r.schedule_status == "scheduled" for r in statuses),
        "waitlisted": sum(r.schedule_status == "waitlisted" for r in statuses),
        "items": [
            {
                "candidate_id": str(r.id),
                "status": r.schedule_status,
                "reason": r.waitlist_reason,
            }
            for r in statuses
        ],
    }
