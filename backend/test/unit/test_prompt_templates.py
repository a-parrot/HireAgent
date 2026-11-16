import json

import httpx
import pytest
from langchain_core.prompts import ChatPromptTemplate
from pydantic import SecretStr

from app.clients.llm_client import LLMClient
from app.core.config import Settings
from app.prompts.prompt_loader import load_prompt, prompt_version, render_messages
from app.schemas.agents import (
    Analysis,
    Evaluation,
    HardConditionScreening,
    ScoringEvidence,
    Verification,
)


@pytest.mark.parametrize(
    ("name", "schema", "payload"),
    [
        (
            "resume_analysis",
            Analysis,
            {
                "pages": [
                    {"file_id": "test", "page_no": 1, "text": "literal {rules} text"}
                ],
                "chunk_prefix": "p1_",
            },
        ),
        ("candidate_evaluation", Evaluation, {"facts": [], "evidence": []}),
        ("hard_condition_screening", HardConditionScreening, {"pages": []}),
        ("hard_condition_review", HardConditionScreening, {"pages": []}),
        (
            "scoring_evidence_review",
            ScoringEvidence,
            {"pages": [], "chunk_prefix": "v0_"},
        ),
        ("scoring_evidence", ScoringEvidence, {"pages": [], "chunk_prefix": "score0_"}),
        (
            "evaluation_review",
            Verification,
            {
                "facts": [],
                "evidence": [],
                "evaluation": {"hard_conditions": [], "dimension_scores": []},
            },
        ),
    ],
)
def test_role_template_inputs_and_schema(name, schema, payload):
    rules = {
        "job_name": "自定义测试岗位",
        "dimensions": [
            {
                "id": "custom",
                "name": "自定义维度",
                "max_score": 100,
                "criteria": "招聘人员手动填写的评分标准",
            }
        ],
        "review_threshold": 55,
        "recommend_threshold": 88,
    }
    messages = render_messages(load_prompt(name), {"rules": rules, **payload}, schema)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "自定义测试岗位" not in messages[0]["content"]
    assert "自定义测试岗位" in messages[1]["content"]
    assert "招聘人员手动填写的评分标准" in messages[1]["content"]
    assert '"recommend_threshold": 88' in messages[1]["content"]
    assert (
        json.dumps(schema.model_json_schema(), ensure_ascii=False)
        in messages[0]["content"]
    )
    if name == "resume_analysis":
        assert (
            "literal {rules} text" in messages[1]["content"]
        )  # inserted values are not formatted a second time


def test_template_missing_inputs_fail_early():
    with pytest.raises(ValueError, match="pages"):
        render_messages(load_prompt("resume_analysis"), {"rules": {}}, Analysis)


def test_unknown_template_path_is_not_read():
    with pytest.raises(ValueError, match="未知提示词"):
        load_prompt("../core/config")


def test_versions_identify_each_cached_template():
    versions = [
        prompt_version(name)
        for name in ("resume_analysis", "candidate_evaluation", "evaluation_review")
    ]
    assert all(len(v) == 12 for v in versions)
    assert len(set(versions)) == 3


@pytest.mark.asyncio
async def test_client_sends_rendered_template_messages_without_duplicate_schema():
    config = Settings(
        _env_file=None,
        llm_base_url="https://example.invalid/v1",
        llm_model="test",
        llm_api_key=SecretStr("test-only"),
    )
    client = LLMClient(config)
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"review_notes":[],"needs_human_review":false}'
                        }
                    }
                ]
            },
        )

    await client.http.aclose()
    client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        template = load_prompt("evaluation_review")
        assert isinstance(template, ChatPromptTemplate)
        result = await client.generate(
            template,
            {
                "rules": {"job_name": "another role"},
                "facts": [],
                "evidence": [],
                "evaluation": {},
            },
            Verification,
        )
        assert result["needs_human_review"] is False
        messages = captured[0]["messages"]
        assert len(messages) == 2 and "another role" in messages[1]["content"]
        assert messages[0]["content"].count('"title": "Verification"') == 1
    finally:
        await client.close()
