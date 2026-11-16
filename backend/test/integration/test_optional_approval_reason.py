import httpx
import pytest
from app.models.mysql.entities import Candidate, Review
from sqlalchemy import select
from test.integration.test_evaluation_actions import application
from test.integration.test_evaluation_management import records


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", [None, "", "符合岗位要求"])
async def test_approve_optional_reason(db, tmp_path, reason):
    _, ids = await records(db)
    app = application(db, tmp_path)
    queued = []
    app.state.runtime.enqueue = queued.append
    payload = {"operation": "approve", "review_version": 0, "operator_name": "test"}
    if reason is not None:
        payload["reason"] = reason
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(f"/api/candidates/{ids[1]}/review", json=payload)
        assert response.status_code == 200, response.text
        repeated = await client.post(f"/api/candidates/{ids[1]}/review", json=payload)
        assert repeated.status_code == 409
    async with db.session() as session:
        candidate = await session.get(Candidate, ids[1])
        review = await session.scalar(
            select(Review).where(Review.candidate_id == ids[1])
        )
        assert candidate.review_status == "approved"
        assert review.reason == (reason or "")
    assert queued == [ids[1]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,review_status,score",
    [
        ("completed", "pending", None),
        ("completed", "deferred", 10),
        ("failed", "pending", None),
        ("pending", "pending", None),
    ],
)
async def test_approve_rejected_or_unscored_then_book(
    db, tmp_path, status, review_status, score
):
    _, ids = await records(db)
    async with db.session() as session:
        candidate = await session.get(Candidate, ids[1])
        candidate.processing_status = status
        candidate.review_status = review_status
        candidate.total_score = score
        candidate.recommendation = "deferred"
    app = application(db, tmp_path)
    app.state.runtime.enqueue = lambda cid: pytest.fail(
        "Manual override must not restart failed/completed evaluation"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/candidates/{ids[1]}/review",
            json={"operation": "approve", "review_version": 0, "operator_name": "test"},
        )
        assert response.status_code == 200, response.text
        listed = await client.get("/api/interviews")
        assert any(
            str(r["candidate"]["id"]) == str(ids[1]) for r in listed.json()["items"]
        )
        booked = await client.post(
            "/api/interviews",
            json={
                "candidate_ids": [ids[1]],
                "starts_at": "2032-01-01T09:00:00+08:00",
                "ends_at": "2032-01-01T09:45:00+08:00",
            },
        )
        assert booked.status_code == 201, booked.text
    async with db.session() as session:
        candidate = await session.get(Candidate, ids[1])
        assert candidate.processing_status == status
        assert candidate.recommendation == "deferred"
        assert candidate.total_score == score
