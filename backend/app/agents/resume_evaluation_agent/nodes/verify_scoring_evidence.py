"""Re-read complete criteria and original text, correcting both false and missed matches."""

from app.agents.resume_evaluation_agent.nodes import extract_scoring_evidence
from app.prompts.prompt_loader import prompt_version


async def run(runtime, state):
    return await extract_scoring_evidence.run(runtime, state, verify=True)


def save(candidate, output, config):
    extract_scoring_evidence.save(candidate, output, config)
    candidate.prompt_versions = {
        **candidate.prompt_versions,
        "scoring_evidence_review": prompt_version("scoring_evidence_review"),
    }
