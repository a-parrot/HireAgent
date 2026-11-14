import asyncio

from app.core.errors import BusinessError
from app.models.mysql.entities import Candidate, Event, Review
from app.repositories.common import require, serialize


async def review_candidate(db, runtime, candidate_id, data):
    async with (
        runtime.locks.setdefault(candidate_id, asyncio.Lock()),
        db.session() as session,
    ):
        candidate = await require(session, Candidate, candidate_id, lock=True)
        if candidate.review_version != data.review_version:
            raise BusinessError("审批版本已变化，请刷新", 409)
        if (
            candidate.processing_status != "waiting_review"
            or candidate.review_status != "pending"
        ):
            raise BusinessError("候选人当前不处于待审核状态", 409)
        if data.operation == "approve" and candidate.total_score is None:
            raise BusinessError("没有有效评分，不能批准排期", 409)
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
            if data.operation == "supplement"
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
    if data.operation != "supplement":
        runtime.enqueue(candidate_id)
    return result
