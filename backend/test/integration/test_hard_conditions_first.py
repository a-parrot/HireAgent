"""Generated PDF + isolated DB: strict gating, fixed points, and source quotes."""

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from app.models.mysql.entities import NodeExecution
from app.services.resume_service.resumes import candidate_detail, candidates
from app.services.workflow_service import operations
from test.integration.test_business import batch, runtime

pytestmark = pytest.mark.asyncio


async def prepare(db, tmp_path, saver=None):
    bid = await batch(db, tmp_path, legacy=False)
    cid = int((await candidates(db, bid))["items"][0]["id"])
    return await runtime(db, tmp_path, saver), cid


async def test_hard_failure_ends_without_scoring_and_reports_exact_condition(
    db, tmp_path
):
    r, cid = await prepare(db, tmp_path)
    generate = r.llm.generate

    async def fail_hard(prompt, payload, schema):
        assert schema.__name__ == "HardConditionScreening"
        result = await generate(prompt, payload, schema)
        result["hard_conditions"][0].update(
            result="unsatisfied", reason="原文工作领域与目标要求不符"
        )
        return result

    r.llm.generate = fail_hard
    try:
        await r.run(cid)
        detail = await candidate_detail(db, cid)
        assert detail["processing_status"] == "completed"
        assert detail["recommendation"] == "deferred"
        assert not detail["needs_human_review"]
        assert detail["total_score"] is None and detail["dimension_scores"] == []
        assert "具备相关领域经验" in detail["review_notes"][0]
        assert detail["hard_conditions"][0]["condition_name"] == "具备相关领域经验"
        assert (
            detail["evidence"][0]["quote"]
            == "Managed overseas modular projects for 12 years."
        )
        assert r.llm.calls == ["HardConditionScreening", "HardConditionScreening"]
        async with db.session() as s:
            assert (await s.scalars(select(NodeExecution.node_name))).all() == [
                "parse_pdf",
                "screen_hard_conditions",
                "verify_hard_conditions",
            ]
    finally:
        await r.close()


async def test_complete_document_non_match_rejects_without_fabricated_evidence(
    db, tmp_path
):
    r, cid = await prepare(db, tmp_path)
    generate = r.llm.generate

    async def no_match(prompt, payload, schema):
        result = await generate(prompt, payload, schema)
        if schema.__name__ == "HardConditionScreening":
            result["hard_conditions"][0].update(
                result="unknown",
                basis="not_found",
                reason="未体现相关领域经验",
                evidence_ids=[],
            )
        return result

    r.llm.generate = no_match
    try:
        await r.run(cid)
        detail = await candidate_detail(db, cid)
        assert detail["recommendation"] == "deferred"
        assert not detail["needs_human_review"]
        assert detail["processing_status"] == "completed"
        assert detail["total_score"] is None
        item = detail["hard_conditions"][0]
        assert item["result"] == "unsatisfied" and item["basis"] == "not_found"
        assert item["evidence_ids"] == [] and item["blocking"]
        assert "简历未匹配到" in item["reason"]
        assert r.llm.calls == ["HardConditionScreening", "HardConditionScreening"]
    finally:
        await r.close()


async def test_non_match_in_passed_or_group_does_not_reject_candidate(db, tmp_path):
    r, cid = await prepare(db, tmp_path)
    generate = r.llm.generate
    rules = await r.rules(cid)
    from app.agents.resume_evaluation_agent.scoring import condition_leaves

    group = next(
        node
        for node in rules["hard_conditions"]["items"]
        if node.get("operator") == "any"
    )
    alternative = condition_leaves(group)[-1]["id"]

    async def no_match_alternative(prompt, payload, schema):
        result = await generate(prompt, payload, schema)
        if schema.__name__ == "HardConditionScreening":
            for item in result["hard_conditions"]:
                if item["condition_id"] == alternative:
                    item.update(
                        result="unsatisfied",
                        basis="not_found",
                        reason="未匹配",
                        evidence_ids=[],
                    )
        return result

    r.llm.generate = no_match_alternative
    try:
        await r.run(cid)
        detail = await candidate_detail(db, cid)
        assert detail["total_score"] == 85
        assert detail["recommendation"] == "recommended"
        assert not next(
            item
            for item in detail["hard_conditions"]
            if item["condition_id"] == alternative
        )["blocking"]
    finally:
        await r.close()


@pytest.mark.parametrize(
    "earned,expected,total",
    [
        ([], "deferred", 0),
        ([0, 2, 3], "needs_review", 60),
        ([0, 2, 3, 4, 5], "recommended", 75),
        (list(range(8)), "recommended", 85),
    ],
)
async def test_fixed_points_and_thresholds_with_real_source_quotes(
    db, tmp_path, earned, expected, total
):
    r, cid = await prepare(db, tmp_path)
    generate = r.llm.generate

    async def match_some(prompt, payload, schema):
        result = await generate(prompt, payload, schema)
        if schema.__name__ == "ScoringEvidence":
            for i, item in enumerate(result["matches"]):
                item.update(matched=i in earned, score=99.9)
        return result

    r.llm.generate = match_some
    try:
        await r.run(cid)
        detail = await candidate_detail(db, cid)
        assert detail["total_score"] == total
        assert detail["recommendation"] == expected
        assert r.llm.calls == [
            "HardConditionScreening",
            "HardConditionScreening",
            "ScoringEvidence",
            "ScoringEvidence",
        ]
        assert len(detail["dimension_scores"]) == 8
        for score in detail["dimension_scores"]:
            assert score["score"] in (0, score["max_score"])
            assert score["dimension_name"]
            if score["score"]:
                assert score["evidence_ids"]
                for eid in score["evidence_ids"]:
                    assert (
                        next(e for e in detail["evidence"] if e["evidence_id"] == eid)[
                            "quote"
                        ]
                        == "Managed overseas modular projects for 12 years."
                    )
            else:
                assert score["evidence_ids"] == []
    finally:
        await r.close()


async def test_unverifiable_hard_condition_rejects_without_scoring(db, tmp_path):
    r, cid = await prepare(db, tmp_path)
    generate = r.llm.generate

    async def invalid_evidence(prompt, payload, schema):
        result = await generate(prompt, payload, schema)
        result["evidence"][0]["quote"] = "Invented text, absent from the PDF"
        return result

    r.llm.generate = invalid_evidence
    try:
        await r.run(cid)
        detail = await candidate_detail(db, cid)
        assert all(c["result"] == "unsatisfied" for c in detail["hard_conditions"])
        assert detail["total_score"] is None
        assert detail["dimension_scores"] == []
        assert detail["recommendation"] == "deferred"
        assert detail["processing_status"] == "completed"
        assert detail["evidence"] == []
    finally:
        await r.close()


async def test_resume_new_human_pause_without_model_calls(db, tmp_path):
    saver = InMemorySaver()
    r, cid = await prepare(db, tmp_path, saver)
    generate = r.llm.generate

    async def unknown(prompt, payload, schema):
        result = await generate(prompt, payload, schema)
        if schema.__name__ == "ScoringEvidence":
            for i, item in enumerate(result["matches"]):
                item["matched"] = i in (0, 2, 3)
        return result

    r.llm.generate = unknown
    try:
        await r.run(cid)
        assert (await candidate_detail(db, cid))[
            "processing_status"
        ] == "waiting_review"
    finally:
        await r.close()
    restarted = await runtime(db, tmp_path, saver)
    try:
        await restarted.run(cid)
        assert (await candidate_detail(db, cid))[
            "processing_status"
        ] == "waiting_review"
        assert restarted.llm.calls == []
    finally:
        await restarted.close()


async def test_cached_recovery_new_flow_rebuilds_lost_checkpoint_without_models(
    db, tmp_path
):
    from app.models.mysql.entities import Candidate

    saver = InMemorySaver()
    r, cid = await prepare(db, tmp_path, saver)
    generate = r.llm.generate

    async def middle(prompt, payload, schema):
        result = await generate(prompt, payload, schema)
        if schema.__name__ == "ScoringEvidence":
            for i, item in enumerate(result["matches"]):
                item["matched"] = i in (0, 2, 3)
        return result

    r.llm.generate = middle
    try:
        await r.run(cid)
        async with db.session() as s:
            c = await s.get(Candidate, cid)
            thread = c.workflow_id
            c.processing_status, c.error_node = "failed", "human_review"
        await saver.adelete_thread(thread)

        async def reject(*args):
            raise AssertionError("no model calls during cached recovery")

        r.llm.generate = reject
        await operations.retry(db, r, cid, cached_review_only=True)
        await r.tasks[cid]
        detail = await candidate_detail(db, cid)
        assert detail["processing_status"] == "waiting_review"
        assert detail["total_score"] == 60
    finally:
        await r.close()
