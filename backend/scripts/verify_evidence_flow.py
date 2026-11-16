"""Live synthetic-only check; never touches business records or real resumes."""

import asyncio
import json
from types import SimpleNamespace

from app.agents.resume_evaluation_agent.nodes import (
    calculate_score,
    extract_scoring_evidence,
    screen_hard_conditions,
    verify_hard_conditions,
    verify_scoring_evidence,
)
from app.clients.llm_client import LLMClient
from app.core.config import Settings


async def main():
    config = Settings()
    llm = LLMClient(config)
    rules = {
        "job_name": "钢结构项目负责人",
        "responsibilities": "管理钢结构项目",
        "requirements": "",
        "hard_conditions": {
            "operator": "all",
            "items": [
                {"id": "domain", "description": "具备钢结构相关领域经验"},
                {"id": "years", "description": "8年以上工作经验或5年以上直接相关经验"},
                {"id": "management", "description": "具备项目或团队管理经历"},
            ],
        },
        "dimensions": [
            {
                "id": "steel_full_cycle",
                "name": "钢结构项目全流程经验",
                "criteria": "同时具备钢结构项目与全流程管理职责",
                "max_score": 100,
            }
        ],
        "recommend_threshold": 75,
        "review_threshold": 60,
    }

    async def get_rules(_):
        return rules

    runtime = SimpleNamespace(config=config, llm=llm, rules=get_rules)
    state = {
        "candidate_id": 0,
        "pages": [
            {
                "file_id": "synthetic",
                "block_id": "document",
                "page_no": None,
                "text": "匿名测试人员。19年工作经验。曾任房地产土建项目负责人，负责从土方开挖到竣工验收交付的全周期管理，带领12人团队，协调资源并制定项目计划。",
            }
        ],
    }
    try:
        state.update(await screen_hard_conditions.run(runtime, state))
        state.update(await verify_hard_conditions.run(runtime, state))
        conditions = {
            item["condition_id"]: item["result"]
            for item in state["screening"]["hard_conditions"]
        }
        # Exercise the scoring stages separately even though the hard domain gate failed.
        state.update(await extract_scoring_evidence.run(runtime, state))
        state.update(await verify_scoring_evidence.run(runtime, state))
        state.update(await calculate_score.run(runtime, state))
        print(
            json.dumps(
                {
                    "model": config.llm_model,
                    "conditions": conditions,
                    "steel_full_cycle_score": state["summary"]["total_score"],
                },
                ensure_ascii=True,
            )
        )
        assert conditions == {
            "domain": "unsatisfied",
            "years": "satisfied",
            "management": "satisfied",
        }
        assert state["summary"]["total_score"] == 0
        print("Synthetic source-to-rule verification passed")
    finally:
        await llm.close()


if __name__ == "__main__":
    asyncio.run(main())
