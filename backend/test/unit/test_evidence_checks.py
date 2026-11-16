import pytest

from app.agents.resume_evaluation_agent.evidence_checks import (
    domain_supported,
    explicit_work_years,
)


def pages(text):
    return [{"file_id": "1", "block_id": "document", "page_no": None, "text": text}]


def test_explicit_years_satisfy_generic_alternative_not_specialist_industry():
    source = pages("19年工作经验，带团队管理实践。")
    result = explicit_work_years("8 年以上工作经验或 5 年以上直接相关经验", source)
    assert result and result[1] == "19年工作经验"
    assert explicit_work_years("5年以上直接相关工作经验", source) is None
    assert explicit_work_years("钢结构行业8年以上工作经验", source) is None


@pytest.mark.parametrize(
    "text",
    [
        "无19年工作经验",
        "招聘要求19年工作经验",
        "不足19年工作经验",
        "年龄43岁",
        "3年工作经验",
    ],
)
def test_negation_requirements_age_and_insufficient_years_do_not_prove_experience(text):
    assert explicit_work_years("8年以上工作经验", pages(text)) is None


def test_generic_full_cycle_cannot_replace_structural_steel_full_cycle():
    rule = {"name": "钢结构项目全流程经验"}
    assert not domain_supported(
        rule, [{"quote": "负责房地产项目从土方开挖到竣工验收的全过程管理"}]
    )
    assert domain_supported(
        rule, [{"quote": "Led structural steel projects from design to delivery"}]
    )
    assert domain_supported(
        {"name": "直接钢结构 MiC / 模块化建筑经验"},
        [{"quote": "Managed modular construction projects"}],
    )
