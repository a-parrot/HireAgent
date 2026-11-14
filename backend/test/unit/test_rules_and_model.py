import json

import httpx
import pytest
from pydantic import SecretStr

from app.agents.recruitment_agent.nodes.summarize_result import combine, summarize
from app.clients.llm_client import LLMClient
from app.core.config import BACKEND_DIR, Settings
from app.core.errors import BusinessError
from app.schemas.agents import Verification
from app.services.job_service.jobs import condition_ids


def inputs(score):
    rules = json.loads(
        (BACKEND_DIR / "app/conf/initial_job.json").read_text(encoding="utf-8")
    )
    pages = [{"file_id": "1", "page_no": 1, "text": "Managed overseas projects"}]
    analysis = {
        "facts": [{"fact_id": "f", "evidence_ids": ["e"]}],
        "evidence": [
            {
                "evidence_id": "e",
                "file_id": "1",
                "page_no": 1,
                "quote": "Managed overseas projects",
            }
        ],
    }
    evaluation = {
        "hard_conditions": [
            {"condition_id": i, "result": "satisfied", "evidence_ids": ["e"]}
            for i in condition_ids(rules["hard_conditions"])
        ],
        "dimension_scores": [
            {
                "dimension_id": d["id"],
                "score": d["max_score"] * score / 100,
                "evidence_ids": ["e"],
            }
            for d in rules["dimensions"]
        ],
        "missing_fields": [],
    }
    return (
        rules,
        pages,
        analysis,
        evaluation,
        {"review_notes": [], "needs_human_review": False},
    )


@pytest.mark.parametrize(
    ("score", "expected"),
    [(75, "recommended"), (74, "needs_review"), (60, "needs_review"), (59, "deferred")],
)
def test_thresholds(score, expected):
    assert summarize(*inputs(score))["recommendation"] == expected


def test_missing_and_hard_conditions_precede_score():
    data = inputs(100)
    data[3]["hard_conditions"][0]["result"] = "unsatisfied"
    assert summarize(*data)["recommendation"] == "deferred"
    data[3]["missing_fields"] = ["management evidence"]
    assert summarize(*data)["recommendation"] == "needs_review"


def test_invalid_evidence_and_invalid_score():
    data = inputs(100)
    data[2]["evidence"][0]["quote"] = "not in source"
    assert summarize(*data)["needs_human_review"]
    data[3]["dimension_scores"][0]["score"] = 101
    assert summarize(*data)["total_score"] is None


def test_any_condition_with_unknown_alternative():
    tree = {"operator": "any", "items": [{"id": "a"}, {"id": "b"}]}
    assert combine(tree, {"a": "satisfied", "b": "unknown"}) == "satisfied"
    assert combine(tree, {"a": "unsatisfied", "b": "unknown"}) == "unknown"


@pytest.mark.asyncio
async def test_dashscope_protocol_and_redacted_access_error():
    config = Settings(
        _env_file=None,
        llm_base_url="https://example.invalid/v1",
        llm_api_key=SecretStr("private-test-key"),
        llm_model="test",
        llm_provider="dashscope",
    )
    client = LLMClient(config)

    def handler(request):
        payload = json.loads(request.content)
        assert payload["enable_thinking"] is False
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": "AccessDenied.Unpurchased",
                    "message": "private-test-key",
                }
            },
        )

    await client.http.aclose()
    client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(BusinessError, match="AccessDenied.Unpurchased") as error:
            await client.generate("JSON", {}, Verification)
        assert "private-test-key" not in str(error.value)
    finally:
        await client.close()
