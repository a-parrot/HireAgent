from app.prompts.prompt_loader import load_prompt, prompt_version
from app.schemas.agents import Verification


class EvaluationReviewAgent:
    async def run(self, llm, rules, analysis, evaluation):
        return await llm.generate(
            load_prompt("evaluation_review"),
            {
                "rules": rules,
                "facts": analysis["facts"],
                "evidence": analysis["evidence"],
                "evaluation": evaluation,
            },
            Verification,
        )


async def run(runtime, state):
    rules = await runtime.rules(state["candidate_id"])
    return {
        "verification": await EvaluationReviewAgent().run(
            runtime.llm, rules, state["analysis"], state["evaluation"]
        )
    }


def save(candidate, output, config):
    candidate.prompt_versions = {
        **(candidate.prompt_versions or {}),
        "review": prompt_version("evaluation_review"),
    }
