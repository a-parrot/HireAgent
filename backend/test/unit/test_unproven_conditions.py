from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.resume_evaluation_agent.nodes.screen_hard_conditions import run


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result,basis,ids",
    [
        ("unknown", "uncertain", []),
        ("satisfied", "evidence", []),
        ("unsatisfied", "not_found", ["e1"]),
        ("satisfied", "evidence", ["absent"]),
    ],
)
async def test_unproven_condition_is_unsatisfied_with_honest_reason(result, basis, ids):
    runtime = SimpleNamespace(
        config=SimpleNamespace(llm_document_chars=30000),
        rules=AsyncMock(
            return_value={
                "hard_conditions": {
                    "operator": "all",
                    "items": [{"id": "management", "description": "具有项目管理经验"}],
                }
            }
        ),
        llm=SimpleNamespace(
            generate=AsyncMock(
                return_value={
                    "name": None,
                    "hard_conditions": [
                        {
                            "condition_id": "management",
                            "result": result,
                            "basis": basis,
                            "reason": "模型判定",
                            "evidence_ids": ids,
                        }
                    ],
                    "evidence": [
                        {
                            "evidence_id": "e1",
                            "file_id": "1",
                            "block_id": "document",
                            "quote": "从事财务工作",
                        }
                    ],
                }
            )
        ),
    )
    output = await run(
        runtime,
        {
            "candidate_id": 1,
            "pages": [
                {"file_id": "1", "block_id": "document", "text": "从事财务工作"},
            ],
        },
    )
    item = output["screening"]["hard_conditions"][0]
    assert item["result"] == "unsatisfied"
    assert item["evidence_ids"] == []
    assert "有效原文依据" in item["reason"]
    assert output["summary"]["recommendation"] == "deferred"
    assert not output["summary"]["needs_human_review"]
