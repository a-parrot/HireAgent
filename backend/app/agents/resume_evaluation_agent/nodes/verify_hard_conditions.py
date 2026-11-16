"""Independently re-read every hard condition before allowing a rejection."""

from app.agents.resume_evaluation_agent.nodes import screen_hard_conditions
from app.prompts.prompt_loader import prompt_version


async def run(runtime, state):
    return await screen_hard_conditions.run(runtime, state, verify=True)


def save(candidate, output, config):
    screen_hard_conditions.save(candidate, output, config)
    candidate.prompt_versions = {
        **candidate.prompt_versions,
        "hard_condition_review": prompt_version("hard_condition_review"),
    }
