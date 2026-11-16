import asyncio
from contextlib import nullcontext

from app.core.errors import BusinessError
from app.core.logging import logger, traced
from app.models.mysql.entities import Candidate, Event, Review
from app.repositories.common import require, serialize
from app.repositories.evaluation_repo.visibility import ensure_visible


@traced("review.decision", agent="human_review", id_arg="candidate_id")
async def review_candidate(db, runtime, candidate_id, data):
    async with (
        (
            nullcontext()
            if data.operation == "approve"
            else runtime.locks.setdefault(candidate_id, asyncio.Lock())
        ),
        db.session() as session,
    ):
        candidate = await require(session, Candidate, candidate_id, lock=True)
        await ensure_visible(session, candidate_id)
        if candidate.review_version != data.review_version:
            raise BusinessError("审批版本已变化，请刷新", 409)
        resume_workflow = (
            candidate.processing_status == "waiting_review"
            and candidate.review_status == "pending"
        )
        if data.operation == "approve":
            if candidate.review_status == "approved":
                raise BusinessError("候选人已批准面试，请刷新", 409)
        elif not resume_workflow:
            raise BusinessError("候选人当前不处于待审核状态", 409)
        if data.supplements and any(
            not s.get("source") or not s.get("description") for s in data.supplements
        ):
            raise BusinessError("补充事实必须包含 description 与 source")
        if data.operation == "supplement" and not data.supplements:
            raise BusinessError("请填写补充内容及来源")
        candidate.review_version += 1
        row = Review(
            candidate_id=candidate_id,
            operation=data.operation,
            review_version=candidate.review_version,
            reason=data.reason,
            supplements=data.supplements,
            operator_name=data.operator_name,
            resume_status="not_required"
            if data.operation == "supplement" or not resume_workflow
            else "pending",
        )
        session.add(row)
        if data.operation != "supplement":
            candidate.review_status = (
                "approved" if data.operation == "approve" else "deferred"
            )
        session.add(
            Event(
                batch_id=candidate.batch_id,
                candidate_id=candidate_id,
                event_type="reviewed",
                message="人工操作：" + data.operation,
            )
        )
        await session.flush()
        result = serialize(row)
    if data.operation != "supplement" and resume_workflow:
        runtime.enqueue(candidate_id)
    logger.bind(
        operation=data.operation,
        review_version=result["review_version"],
        resume_status=result["resume_status"],
    ).info("review.saved")
    return result
