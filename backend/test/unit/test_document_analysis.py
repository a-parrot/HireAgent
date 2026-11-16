from unittest.mock import AsyncMock

import pytest

from app.agents.resume_evaluation_agent.decision import summarize
from app.agents.resume_evaluation_agent.nodes.analyze_resume import ResumeAnalysisAgent
from app.schemas.agents import Evidence
from test.unit.test_rules_and_model import inputs


@pytest.mark.asyncio
async def test_short_document_uses_one_model_call_and_keeps_cross_section_context():
    llm = AsyncMock()
    llm.generate.return_value = {
        "name": None,
        "facts": [],
        "evidence": [],
        "missing_fields": [],
    }
    document = "# 工作经历\n公司 A，2020—2025，项目经理。\n\n# 项目经历\n在公司 A 主导海外交付。"
    await ResumeAnalysisAgent().run(
        llm,
        {},
        [{"file_id": "1", "block_id": "document", "page_no": None, "text": document}],
        1000,
    )
    llm.generate.assert_awaited_once()
    assert llm.generate.await_args.args[1]["pages"][0]["text"] == document


@pytest.mark.asyncio
async def test_long_document_splits_at_sections_not_fixed_character_boundaries():
    llm = AsyncMock()
    llm.generate.return_value = {
        "name": None,
        "facts": [],
        "evidence": [],
        "missing_fields": [],
    }
    sections = [
        "# 项目 A\n" + "负责海外交付。" * 5,
        "# 项目 B\n" + "负责工程管理。" * 5,
    ]
    await ResumeAnalysisAgent().run(
        llm,
        {},
        [{"file_id": "1", "block_id": "document", "text": "\n\n".join(sections)}],
        55,
    )
    assert llm.generate.await_count == 2
    assert sections[0] in llm.generate.await_args_list[0].args[1]["pages"][0]["text"]
    assert sections[1] == llm.generate.await_args_list[1].args[1]["pages"][0]["text"]


@pytest.mark.asyncio
async def test_oversized_single_paragraph_is_not_silently_truncated():
    llm = AsyncMock()
    llm.generate.return_value = {
        "name": None,
        "facts": [],
        "evidence": [],
        "missing_fields": [],
    }
    await ResumeAnalysisAgent().run(
        llm, {}, [{"file_id": "1", "block_id": "document", "text": "A" * 100}], 50
    )
    segments = [
        call.args[1]["pages"][0]["text"] for call in llm.generate.await_args_list
    ]
    assert len(segments) == 3
    assert all(len(segment) <= 50 for segment in segments)
    assert sum(map(len, segments)) >= 100


def test_document_evidence_requires_real_quote_and_valid_block():
    data = inputs(100)
    data[1][0].update(block_id="document", page_no=None)
    data[2]["evidence"][0].update(block_id="document", page_no=None)
    evidence = Evidence.model_validate(data[2]["evidence"][0])
    assert evidence.page_no is None and evidence.block_id == "document"
    assert summarize(*data)["recommendation"] == "recommended"
    data[2]["evidence"][0]["block_id"] = "invented"
    assert summarize(*data)["needs_human_review"]
