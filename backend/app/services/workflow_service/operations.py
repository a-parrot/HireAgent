import asyncio
import csv
import io
import json

from sqlalchemy import select

from app.core.errors import BusinessError
from app.models.mysql.entities import Batch, Candidate, Event, NodeExecution, utcnow
from app.repositories.common import require, serialize
from app.repositories.evaluation_repo.visibility import ensure_visible
from app.services.resume_service.resumes import candidate_detail


async def start_batch(db, runtime, batch_id):
    async with db.session() as session:
        batch = await require(session, Batch, batch_id, lock=True)
        if batch.started_at:
            return {
                "batch_id": str(batch_id),
                "status": batch.status,
                "already_started": True,
            }
        batch.started_at, batch.status = utcnow(), "running"
        ids = list(
            (
                await session.scalars(
                    select(Candidate.id).where(Candidate.batch_id == batch_id)
                )
            ).all()
        )
        session.add(Event(batch_id=batch_id, event_type="started", message="批次启动"))
    for candidate_id in ids:
        runtime.enqueue(candidate_id)
    return {"batch_id": str(batch_id), "status": "running", "already_started": False}


async def retry(db, runtime, candidate_id, *, cached_review_only=False):
    async with (
        runtime.locks.setdefault(candidate_id, asyncio.Lock()),
        db.session() as session,
    ):
        candidate = await require(session, Candidate, candidate_id, lock=True)
        await ensure_visible(session, candidate_id)
        if candidate.processing_status != "failed":
            raise BusinessError("仅失败候选人可以重试", 409)
        if cached_review_only:
            from app.agents.resume_evaluation_agent.scoring import (
                FLOW_VERSION,
                LEGACY_FLOW_VERSION,
            )

            batch = await require(session, Batch, candidate.batch_id)
            required = {
                "parse_pdf": "pages",
                "analyze_resume": "analysis",
                "evaluate_candidate": "evaluation",
                "route_candidate": "summary",
                "review_evaluation": "verification",
                "summarize_result": "summary",
            }
            if batch.rule_snapshot.get("evaluation_flow") in (
                FLOW_VERSION,
                LEGACY_FLOW_VERSION,
            ):
                required = {
                    "parse_pdf": "pages",
                    "screen_hard_conditions": "screening",
                    "extract_scoring_evidence": "analysis",
                    "calculate_score": "summary",
                }
                if batch.rule_snapshot.get("evaluation_flow") == FLOW_VERSION:
                    required.update(
                        verify_hard_conditions="screening",
                        verify_scoring_evidence="analysis",
                    )
            rows = (
                await session.execute(
                    select(NodeExecution.node_name, NodeExecution.output_data).where(
                        NodeExecution.candidate_id == candidate_id,
                        NodeExecution.status == "succeeded",
                    )
                )
            ).all()
            saved = {
                name
                for name, output in rows
                if name in required
                and isinstance(output, dict)
                and isinstance(
                    output.get(required[name]), list if name == "parse_pdf" else dict
                )
                and output[required[name]]
            }
            if (
                candidate.error_node != "human_review"
                or candidate.review_status != "pending"
                or candidate.recommendation != "needs_review"
                or not required.keys() <= saved
            ):
                raise BusinessError("缺少完整的已保存评估结果，不能无模型恢复审核", 409)
        candidate.retry_count += 1
        candidate.processing_status = "pending"
        batch = await require(session, Batch, candidate.batch_id, lock=True)
        batch.status = "running"
        batch.evaluation_completed_at = None
        session.add(
            Event(
                batch_id=batch.id,
                candidate_id=candidate_id,
                event_type="review_recovery_requested"
                if cached_review_only
                else "retried",
                message="复用已保存节点结果恢复待审核，不请求模型"
                if cached_review_only
                else "人工触发失败节点重试",
                attempt_count=candidate.retry_count,
            )
        )
    runtime.enqueue(candidate_id)
    return {"candidate_id": str(candidate_id), "status": "running"}


async def events(db, batch_id, after_id, limit):
    async with db.session() as session:
        await require(session, Batch, batch_id)
        rows = (
            await session.scalars(
                select(Event)
                .where(Event.batch_id == batch_id, Event.id > after_id)
                .order_by(Event.id)
                .limit(limit)
            )
        ).all()
        return {
            "items": [serialize(r) for r in rows],
            "next_cursor": str(rows[-1].id) if rows else str(after_id),
        }


def csv_safe(value):
    value = "" if value is None else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(
        ("\t", "\r")
    ):
        return "'" + value
    return value


async def export(db, batch_id, format, candidate_id=None):
    async with db.session() as session:
        batch = await require(session, Batch, batch_id)
        batch_data = serialize(batch)
        query = select(Candidate.id).where(Candidate.batch_id == batch_id)
        if candidate_id is not None:
            query = query.where(Candidate.id == candidate_id)
        ids = list((await session.scalars(query.order_by(Candidate.id))).all())
    items = [await candidate_detail(db, i) for i in ids]
    if format == "json":
        return json.dumps(
            {"batch": batch_data, "candidates": items}, ensure_ascii=False, indent=2
        ).encode(), "application/json"
    dims = batch_data["rule_snapshot"]["dimensions"]
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "candidate_id",
            "name",
            "rule_version_id",
            "processing_status",
            "recommendation",
            "total_score",
        ]
        + [csv_safe(d["name"]) for d in dims]
        + [
            "hard_conditions",
            "evidence",
            "missing_fields",
            "risks",
            "review_notes",
            "review_history",
            "schedule_status",
            "waitlist_reason",
            "reservation",
            "actions",
            "error_message",
        ]
    )
    for c in items:
        scores = {s["dimension_id"]: s["score"] for s in c["dimension_scores"] or []}
        values = (
            [
                c[k]
                for k in (
                    "id",
                    "name",
                    "rule_version_id",
                    "processing_status",
                    "recommendation",
                    "total_score",
                )
            ]
            + [scores.get(d["id"]) for d in dims]
            + [
                json.dumps(c[k], ensure_ascii=False)
                if isinstance(c[k], (list, dict))
                else c[k]
                for k in (
                    "hard_conditions",
                    "evidence",
                    "missing_fields",
                    "risks",
                    "review_notes",
                    "review_history",
                    "schedule_status",
                    "waitlist_reason",
                    "reservation",
                    "actions",
                    "error_message",
                )
            ]
        )
        writer.writerow([csv_safe(v) for v in values])
    return output.getvalue().encode("utf-8-sig"), "text/csv"
