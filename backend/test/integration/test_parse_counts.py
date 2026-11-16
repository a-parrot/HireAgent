import pytest

from app.services.resume_service import workspace
from scripts.seed_job import seed
from test.integration.test_business import pdf
from test.integration.test_resume_workspace import ready


@pytest.mark.asyncio
async def test_multiple_parsed_resumes_are_counted_as_integer_not_boolean(db, tmp_path):
    jid, _ = await seed(db)
    for _ in range(3):
        await ready(db, tmp_path, int(jid), pdf())
    result = (await workspace.job_summary(db))["items"][0]
    assert result["resume_count"] == 3
    assert result["parsed_count"] == 3
