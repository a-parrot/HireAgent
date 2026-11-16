from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.resume_evaluation_agent.nodes.analyze_resume import document_chunks
from app.agents.resume_evaluation_agent.nodes.screen_hard_conditions import run


def test_single_large_paragraph_keeps_all_characters_and_source_ids():
    text = "".join(chr(0x4E00 + i) for i in range(200))
    chunks = document_chunks(
        [{"file_id": "1", "block_id": "document", "text": text}], 50
    )
    for chunk in chunks:
        assert sum(len(p["text"]) for p in chunk) <= 50
        assert all(p["text"] in text and p["block_id"] == "document" for p in chunk)
    assert set("".join(p["text"] for c in chunks for p in c)) == set(text)


@pytest.mark.asyncio
@pytest.mark.parametrize("verify", [False, True])
async def test_last_fragment_match_overrides_earlier_nonmatches(verify):
    text = "普通经历，负责执行。" * 3 + "\n\n" + "负责团队管理及项目交付。"
    source = {"file_id": "1", "block_id": "document", "text": text}
    report = AsyncMock()
    calls = []

    async def generate(prompt, payload, schema):
        chunk = payload["pages"][0]
        calls.append(chunk["text"])
        matched = "团队管理" in chunk["text"]
        return {
            "name": None,
            "hard_conditions": [
                {
                    "condition_id": "management",
                    "result": "satisfied" if matched else "unsatisfied",
                    "basis": "evidence" if matched else "not_found",
                    "reason": "本段匹配" if matched else "本段未匹配",
                    "evidence_ids": ["same_id"] if matched else [],
                }
            ],
            "evidence": [
                {
                    "evidence_id": "same_id",
                    "file_id": "1",
                    "block_id": "document",
                    "quote": "负责团队管理及项目交付。",
                }
            ]
            if matched
            else [],
        }

    runtime = SimpleNamespace(
        config=SimpleNamespace(llm_document_chars=32),
        rules=AsyncMock(
            return_value={
                "hard_conditions": {
                    "operator": "all",
                    "items": [
                        {"id": "management", "description": "具备团队管理经验"},
                    ],
                }
            }
        ),
        llm=SimpleNamespace(generate=generate),
        report_progress=report,
    )
    result = await run(runtime, {"candidate_id": 1, "pages": [source]}, verify=verify)
    assert len(calls) >= 2
    assert all(len(chunk) <= 32 for chunk in calls)
    assert result["screening"]["result"] == "satisfied"
    condition = result["screening"]["hard_conditions"][0]
    assert condition["evidence_ids"]
    assert result["analysis"]["evidence"][0]["quote"] in text
    assert report.await_count == len(calls)
    assert report.await_args.args[2:] == (len(calls), len(calls))
