from sqlalchemy import func, select

from app.models.mysql.entities import Job, JobRuleVersion
from app.repositories.common import require


async def get_job(session, job_id, lock=False):
    return await require(session, Job, job_id, lock=lock)


async def page_jobs(session, page, page_size):
    total = await session.scalar(select(func.count()).select_from(Job))
    rows = (
        await session.scalars(
            select(Job)
            .order_by(Job.id.desc())
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
