import asyncio
from types import SimpleNamespace

import pytest

from app.services.resume_service.resumes import candidate_detail, candidates
from test.integration.test_business import batch, runtime


@pytest.mark.asyncio
async def test_waiting_candidate_stays_pending_until_previous_resume_finishes(
    db, tmp_path
):
    ids = []
    for _ in range(2):
        bid = await batch(db, tmp_path)
        ids.append(int((await candidates(db, bid))["items"][0]["id"]))
    r = await runtime(db, tmp_path)
    assert r.config.model_concurrency == r.config.import_concurrency == 1
    entered, release = asyncio.Event(), asyncio.Event()
    active, peak, count = 0, 0, 0

    async def get_state(config):
        return SimpleNamespace(interrupts=[], values={})

    async def invoke(value, config):
        nonlocal active, peak, count
        active += 1
        count += 1
        peak = max(peak, active)
        if count == 1:
            entered.set()
            await release.wait()
        active -= 1
        return {}

    r.graph = SimpleNamespace(aget_state=get_state, ainvoke=invoke)
    try:
        for cid in ids:
            r.enqueue(cid)
        await asyncio.wait_for(entered.wait(), 3)
        assert (await candidate_detail(db, ids[1]))["processing_status"] == "pending"
        release.set()
        await asyncio.gather(*(r.tasks[cid] for cid in ids))
        assert peak == 1 and count == 2
    finally:
        release.set()
        await r.close()
