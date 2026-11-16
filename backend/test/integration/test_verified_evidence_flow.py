import pytest

from app.services.resume_service.resumes import candidate_detail
from test.integration.test_hard_conditions_first import prepare

pytestmark = pytest.mark.asyncio


async def test_second_read_corrects_initial_missed_management_evidence(db, tmp_path):
    runtime, cid = await prepare(db, tmp_path)
    generate = runtime.llm.generate
    calls = 0

    async def initially_missed(prompt, payload, schema):
        nonlocal calls
        result = await generate(prompt, payload, schema)
        if schema.__name__ == "HardConditionScreening":
            calls += 1
            if calls == 1:
                for item in result["hard_conditions"]:
                    item.update(
                        result="unsatisfied", basis="not_found", evidence_ids=[]
                    )
        return result

    runtime.llm.generate = initially_missed
    try:
        await runtime.run(cid)
        detail = await candidate_detail(db, cid)
        assert calls == 2
        assert all(item["result"] == "satisfied" for item in detail["hard_conditions"])
        assert detail["total_score"] == 85
        assert detail["prompt_versions"]["hard_condition_review"]
        assert detail["prompt_versions"]["scoring_evidence_review"]
    finally:
        await runtime.close()


async def test_unresolved_disagreement_fails_hard_condition(db, tmp_path):
    runtime, cid = await prepare(db, tmp_path)
    generate = runtime.llm.generate
    calls = 0

    async def conflicting_second_read(prompt, payload, schema):
        nonlocal calls
        result = await generate(prompt, payload, schema)
        if schema.__name__ == "HardConditionScreening":
            calls += 1
            if calls == 2:
                result["hard_conditions"][0].update(
                    result="unsatisfied", basis="not_found", evidence_ids=[]
                )
        return result

    runtime.llm.generate = conflicting_second_read
    try:
        await runtime.run(cid)
        detail = await candidate_detail(db, cid)
        assert detail["processing_status"] == "completed"
        assert detail["recommendation"] == "deferred"
        assert detail["total_score"] is None
        assert detail["hard_conditions"][0]["result"] == "unsatisfied"
        assert detail["hard_conditions"][0]["evidence_ids"] == []
        assert "有效原文依据" in detail["hard_conditions"][0]["reason"]
    finally:
        await runtime.close()
