from app.prompts.prompt_loader import load_prompt, prompt_version
from app.schemas.agents import Evaluation


class CandidateEvaluationAgent:
    async def run(self, llm, rules, analysis):
        # Chunk-local omissions are not global missing fields; the evaluator sees all facts.
        return await llm.generate(
            load_prompt("candidate_evaluation"),
            {
                "rules": rules,
                "facts": analysis["facts"],
                "evidence": analysis["evidence"],
            },
            Evaluation,
        )


async def run(runtime, state):
    rules = await runtime.rules(state["candidate_id"])
    return {
        "evaluation": await CandidateEvaluationAgent().run(
            runtime.llm, rules, state["analysis"]
        )
    }


def save(candidate, output, config):
    result = output["evaluation"]
    candidate.prompt_versions = {
        **(candidate.prompt_versions or {}),
        "evaluation": prompt_version("candidate_evaluation"),
    }
    candidate.hard_conditions, candidate.dimension_scores = (
        result["hard_conditions"],
        result["dimension_scores"],
    )
    candidate.missing_fields, candidate.risks = (
        result["missing_fields"],
        result["risks"],
    )
