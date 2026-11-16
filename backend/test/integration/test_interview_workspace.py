from datetime import datetime

import httpx
import pytest
from sqlalchemy import func, select

from app.models.mysql.entities import ActionRecord, Candidate, Event, Reservation, Slot
from test.integration.test_evaluation_actions import application
from test.integration.test_evaluation_management import records

pytestmark = pytest.mark.asyncio


async def eligible(db):
    _, ids = await records(db)
    async with db.session() as session:
        for cid in ids[:2]:
            candidate = await session.get(Candidate, cid)
            candidate.review_status, candidate.processing_status = (
                "approved",
                "completed",
            )
    return ids


def payload(
    ids,
    start="2032-01-01T09:00:00+08:00",
    end="2032-01-01T09:30:00+08:00",
    interviewer="A",
):
    return {
        "candidate_ids": ids,
        "starts_at": start,
        "ends_at": end,
        "timezone": "Asia/Shanghai",
        "interviewer": interviewer,
        "gap_minutes": 10,
    }


async def test_booking_preview_order_gap_reschedule_and_cancel(db, tmp_path):
    ids = await eligible(db)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application(db, tmp_path)),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/interviews", json=payload(ids[:2]))
        assert response.status_code == 201, response.text
        assert response.json()["scheduled"] == 2
        rows = (await client.get("/api/interviews?status=scheduled")).json()["items"]
        assert [r["candidate"]["id"] for r in rows] == list(map(str, ids[:2]))
        assert rows[0]["slot"]["starts_at"].startswith("2032-01-01T01:00")
        assert rows[1]["slot"]["starts_at"].startswith("2032-01-01T01:40")
        rid = rows[0]["reservation"]["id"]
        body = {
            **payload([], "2032-01-02T10:00:00+08:00", "2032-01-02T11:00:00+08:00"),
            "preview_version": 0,
        }
        assert (
            await client.patch(f"/api/interviews/{rid}", json=body)
        ).status_code == 200
        assert (
            await client.patch(f"/api/interviews/{rid}", json=body)
        ).status_code == 409
        assert (
            await client.delete(f"/api/interviews/{rid}?preview_version=1")
        ).status_code == 200
        pending = (await client.get("/api/interviews?status=pending")).json()
        assert pending["total"] == 1
        assert pending["items"][0]["candidate"]["schedule_status"] == "unscheduled"
    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(Slot)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.event_type == "interview_cancelled")
            )
            == 1
        )


async def test_batch_conflict_rolls_back_every_booking(db, tmp_path):
    ids = await eligible(db)
    # Reserve the second interval in another batch for the same interviewer.
    async with db.session() as session:
        c = await session.get(Candidate, ids[0])
        session.add(
            Slot(
                batch_id=c.batch_id,
                starts_at=datetime(2032, 1, 1, 1, 40),
                ends_at=datetime(2032, 1, 1, 2, 10),
                timezone="Asia/Shanghai",
                interviewer="A",
            )
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application(db, tmp_path)),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/interviews", json=payload(ids[:2]))
        assert response.status_code == 409, response.text
    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(Reservation)) == 0
        assert await session.scalar(select(func.count()).select_from(Slot)) == 1


async def test_external_actions_guard_and_invalid_candidates(db, tmp_path):
    ids = await eligible(db)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application(db, tmp_path)),
        base_url="http://test",
    ) as client:
        assert (
            await client.post("/api/interviews", json=payload([ids[2]]))
        ).status_code == 409
        assert (
            await client.post(
                "/api/interviews",
                json=payload(
                    [ids[0]], "2020-01-01T09:00:00+08:00", "2020-01-01T10:00:00+08:00"
                ),
            )
        ).status_code == 400
        assert (
            await client.post("/api/interviews", json=payload([ids[0]]))
        ).status_code == 201
        assert (
            await client.post("/api/interviews", json=payload([ids[0]]))
        ).status_code == 409
        rid = (await client.get("/api/interviews?status=scheduled")).json()["items"][0][
            "reservation"
        ]["id"]
        async with db.session() as session:
            session.add(
                ActionRecord(
                    reservation_id=int(rid),
                    action_type="meeting",
                    idempotency_key="test-meeting",
                    status="succeeded",
                    attempt_count=1,
                )
            )
        assert not (await client.get("/api/interviews?status=scheduled")).json()[
            "items"
        ][0]["editable"]
        assert (
            await client.delete(f"/api/interviews/{rid}?preview_version=0")
        ).status_code == 409
        body = {
            **payload([], "2032-01-02T09:00:00+08:00", "2032-01-02T10:00:00+08:00"),
            "preview_version": 0,
        }
        assert (
            await client.patch(f"/api/interviews/{rid}", json=body)
        ).status_code == 409


async def test_parallel_interviewers_and_candidate_filter(db, tmp_path):
    ids = await eligible(db)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application(db, tmp_path)),
        base_url="http://test",
    ) as client:
        assert (
            await client.post(
                "/api/interviews", json=payload([ids[0]], interviewer="A")
            )
        ).status_code == 201
        assert (
            await client.post(
                "/api/interviews", json=payload([ids[1]], interviewer="A")
            )
        ).status_code == 409
        response = await client.post(
            "/api/interviews", json=payload([ids[1]], interviewer="B")
        )
        assert response.status_code == 201, response.text
        result = (await client.get(f"/api/interviews?candidate_id={ids[1]}")).json()
        assert result["total"] == 1
        assert result["items"][0]["candidate"]["id"] == str(ids[1])
