from fastapi import APIRouter, Request

from app.schemas.business import ReviewRequest
from app.services.review_service.reviews import review_candidate

router = APIRouter(prefix="/api/candidates", tags=["人工审核"])


@router.post("/{candidate_id}/review")
async def review(request: Request, candidate_id: int, data: ReviewRequest):
    return await review_candidate(
        request.app.state.mysql, request.app.state.runtime, candidate_id, data
    )
