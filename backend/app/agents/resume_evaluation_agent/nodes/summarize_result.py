"""Merge second-review notes and persist the state waiting for a human."""

from app.agents.resume_evaluation_agent.nodes import route_candidate


async def run(runtime, state):
    return await route_candidate.run(runtime, state)


def save(candidate, output, config):
    route_candidate.save(candidate, output, config)
    candidate.processing_status = "waiting_review"
    candidate.current_node = "human_review"
