"""Run from backend: uv run python -m scripts.seed_job."""

import asyncio
import json

from sqlalchemy import select

from app.clients.mysql_client import MySQLClient
from app.core.config import BACKEND_DIR, Settings
from app.models.mysql.entities import Job, JobRuleVersion
from app.services.job_service.jobs import validate_rules


async def seed(db):
    rules = json.loads(
        (BACKEND_DIR / "app/conf/initial_job.json").read_text(encoding="utf-8")
    )
    validate_rules(rules)
    async with db.session() as session:
        job = await session.scalar(
            select(Job).where(Job.code == "overseas_mic_project_lead").with_for_update()
        )
        if job:
            return str(job.id), False
        job = Job(
            code="overseas_mic_project_lead",
            name=rules["job_name"],
            responsibilities=rules["responsibilities"],
            requirements=rules["requirements"],
            draft_rules=rules,
        )
        session.add(job)
        await session.flush()
        session.add(
            JobRuleVersion(
                job_id=job.id,
                version_no=1,
                rule_snapshot=rules,
                published_by="seed_script",
            )
        )
        return str(job.id), True


async def main():
    db = MySQLClient(Settings())
    try:
        job_id, created = await seed(db)
        print(f"job_id={job_id}; created={created}")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
