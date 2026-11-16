"""Opt-in real MySQL migrations and persistent LangGraph recovery.

Requires an explicitly created, dedicated DB_NAME ending in _test.
Uses only test-generated PDFs and a model double; never sends personal data.
"""

import asyncio
import os

import pytest
from alembic.config import Config

from alembic import command
from app.clients.mysql_client import MySQLClient
from app.core.config import BACKEND_DIR, Settings
from app.schemas.business import ReviewRequest
from app.services.resume_service.resumes import candidate_detail, candidates
from app.services.review_service.reviews import review_candidate
from app.services.workflow_service import operations
from app.services.workflow_service.runtime import WorkflowRuntime
from test.integration.test_business import FakeLLM, batch


@pytest.mark.skipif(
    os.getenv("RUN_MYSQL_BACKEND_TESTS") != "1",
    reason="Dedicated MySQL test database required",
)
@pytest.mark.asyncio
async def test_mysql_migration_and_checkpoint_restart(tmp_path):
    config = Settings(storage_dir=tmp_path / "storage")
    if not config.db_name.endswith("_test"):
        pytest.fail("Only a dedicated DB_NAME ending in _test is permitted")
    await asyncio.to_thread(
        command.upgrade, Config(str(BACKEND_DIR / "alembic.ini")), "head"
    )
    db = MySQLClient(config)
    r = WorkflowRuntime(db, config)
    await r.llm.close()
    r.llm = FakeLLM()
    r.llm.uncertain = True
    try:
        await r.start()
        bid = await batch(db, tmp_path)
        cid = int((await candidates(db, bid))["items"][0]["id"])
        await operations.start_batch(db, r, bid)
        await r.tasks[cid]
        assert (await candidate_detail(db, cid))[
            "processing_status"
        ] == "waiting_review"
        r.enqueue = lambda _: None
        await review_candidate(
            db,
            r,
            cid,
            ReviewRequest(
                operation="approve",
                review_version=0,
                reason="dedicated test",
                operator_name="integration-test",
            ),
        )
    finally:
        await r.close()
    restarted = WorkflowRuntime(db, config)
    await restarted.llm.close()
    restarted.llm = FakeLLM()
    try:
        await restarted.start()
        await asyncio.gather(*restarted.tasks.values())
        detail = await candidate_detail(db, cid)
        assert detail["processing_status"] == "completed"
        assert detail["review_history"][0]["resume_status"] == "succeeded"
        assert restarted.llm.calls == []
    finally:
        await restarted.close()
        await db.close()
