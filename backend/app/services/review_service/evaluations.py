"""Post-evaluation workspace, grouped using each immutable scoring snapshot."""

from app.models.mysql.entities import Batch, Candidate, Job, Review
from app.repositories.common import serialize
from app.repositories.evaluation_repo.visibility import visible_candidates
from sqlalchemy import case, func, or_, select

FINISHED = ("completed", "waiting_review", "failed")


async def list_results(
    db,
    *,
    job_id=None,
    keyword=None,
    bucket=None,
    min_score=None,
    max_score=None,
    workflow=None,
    latest_only=True,
    page=1,
    page_size=20,
):
    recommend = func.coalesce(Batch.rule_snapshot["recommend_threshold"].as_float(), 75)
    review = func.coalesce(Batch.rule_snapshot["review_threshold"].as_float(), 60)
    group = case(
        (Candidate.total_score.is_(None), "unscored"),
        (Candidate.total_score >= recommend, "high"),
        (Candidate.total_score >= review, "middle"),
        else_="low",
    )
    query = (
        select(
            Candidate,
            Job.id.label("job_id"),
            Job.name.label("job_name"),
            recommend.label("recommend_threshold"),
            review.label("review_threshold"),
            group.label("score_bucket"),
        )
        .select_from(Candidate)
        .join(Batch, Batch.id == Candidate.batch_id)
        .join(Job, Job.id == Batch.job_id)
        .where(
            Candidate.processing_status.in_(FINISHED),
            Job.deleted_at.is_(None),
            visible_candidates(),
        )
    )
    if latest_only:
        latest = (
            select(func.max(Candidate.id))
            .join(Batch)
            .where(Candidate.processing_status.in_(FINISHED))
            .group_by(Batch.job_id, Candidate.file_id)
        )
        query = query.where(Candidate.id.in_(latest))
    if job_id is not None:
        query = query.where(Job.id == job_id)
    if keyword:
        query = query.where(
            or_(
                Candidate.name.contains(keyword, autoescape=True),
                Candidate.original_filename.contains(keyword, autoescape=True),
            )
        )
    async with db.session() as session:
        grouped = query.with_only_columns(group.label("score_bucket")).subquery()
        counts = dict(
            (
                await session.execute(
                    select(grouped.c.score_bucket, func.count()).group_by(
                        grouped.c.score_bucket
                    )
                )
            ).all()
        )
        thresholds = (
            await session.execute(
                query.with_only_columns(
                    recommend.label("recommend"), review.label("review")
                ).distinct()
            )
        ).all()
        if bucket:
            query = query.where(group == bucket)
        if min_score is not None:
            query = query.where(Candidate.total_score >= min_score)
        if max_score is not None:
            query = query.where(Candidate.total_score <= max_score)
        if workflow == "waiting_review":
            query = query.where(
                Candidate.processing_status == "waiting_review",
                Candidate.review_status == "pending",
            )
        elif workflow == "approved":
            query = query.where(Candidate.review_status == "approved")
        elif workflow == "scheduled":
            query = query.where(Candidate.schedule_status == "scheduled")
        elif workflow == "waitlisted":
            query = query.where(Candidate.schedule_status == "waitlisted")
        elif workflow == "awaiting_schedule":
            query = query.where(
                Candidate.review_status == "approved",
                Candidate.schedule_status != "scheduled",
            )
        elif workflow == "deferred":
            query = query.where(
                or_(
                    Candidate.review_status == "deferred",
                    (Candidate.recommendation == "deferred")
                    & (Candidate.review_status != "approved"),
                )
            )
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        rows = (
            await session.execute(
                query.order_by(
                    Candidate.total_score.is_(None),
                    Candidate.total_score.desc(),
                    Candidate.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        # Fetch final human decisions in one query, including historical records.
        decisions = {}
        ids = [row[0].id for row in rows]
        if ids:
            latest_decisions = (
                select(func.max(Review.id))
                .where(
                    Review.candidate_id.in_(ids),
                    Review.operation.in_(["approve", "defer"]),
                )
                .group_by(Review.candidate_id)
            )
            for decision in (
                await session.scalars(
                    select(Review).where(Review.id.in_(latest_decisions))
                )
            ).all():
                decisions[decision.candidate_id] = serialize(decision)
        return {
            "items": [
                {
                    **serialize(row[0]),
                    "job_id": str(row.job_id),
                    "job_name": row.job_name,
                    "recommend_threshold": float(row.recommend_threshold),
                    "review_threshold": float(row.review_threshold),
                    "score_bucket": row.score_bucket,
                    "manual_review": decisions.get(row[0].id),
                }
                for row in rows
            ],
            "total": total,
            "counts": {
                "all": sum(counts.values()),
                **{
                    key: counts.get(key, 0)
                    for key in ("high", "middle", "low", "unscored")
                },
            },
            "thresholds": [
                {"recommend": float(row.recommend), "review": float(row.review)}
                for row in thresholds
            ],
        }
