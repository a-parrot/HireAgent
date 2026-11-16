from langgraph.types import interrupt

from app.core.errors import BusinessError
from app.core.logging import traced
from app.models.mysql.entities import Candidate
from app.repositories.common import require


@traced("human_review", agent="human_review", state_arg="state")
async def run(runtime, state):
    decision = interrupt(
        {
            "candidate_id": str(state["candidate_id"]),
            "message": "等待人工批准或暂缓",
        }
    )
    async with runtime.db.session() as session:
        candidate = await require(session, Candidate, state["candidate_id"])
        if candidate.review_status not in ("approved", "deferred"):
            raise BusinessError("尚无有效人工决定", 409)
        if decision["operation"] != (
            "approve" if candidate.review_status == "approved" else "defer"
        ):
            raise BusinessError("恢复决定与审批记录不一致", 409)
    return {"decision": decision["operation"]}
