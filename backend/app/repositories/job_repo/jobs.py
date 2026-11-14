from sqlalchemy import func, select

from app.core.errors import BusinessError
from app.models.mysql.entities import Job, JobRuleVersion
from app.repositories.common import require


async def get_job(session, job_id, lock=False):
    job = await require(session, Job, job_id, lock=lock)
    if job.deleted_at is not None:
        raise BusinessError("岗位已删除", 404)
    return job


async def page_jobs(session, page, page_size, keyword=None, status=None):
    query = select(Job).where(Job.deleted_at.is_(None))
    if keyword:
        query = query.where(Job.name.contains(keyword, autoescape=True))
    if status:
        query = query.where(Job.status == status)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await session.scalars(
            query.order_by(Job.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return rows, total


async def versions(session, job_id):
    return (
        await session.scalars(
            select(JobRuleVersion)
            .where(JobRuleVersion.job_id == job_id)
            .order_by(JobRuleVersion.version_no.desc())
        )
    ).all()


async def latest_version_number(session, job_id):
    return (
        await session.scalar(
            select(func.max(JobRuleVersion.version_no)).where(
                JobRuleVersion.job_id == job_id
            )
        )
        or 0
    )


async def latest_versions(session, job_ids):
    if not job_ids:
        return {}
    result = await session.execute(
        select(JobRuleVersion.job_id, func.max(JobRuleVersion.version_no))
        .where(JobRuleVersion.job_id.in_(job_ids))
        .group_by(JobRuleVersion.job_id)
    )
    return dict(result.all())
