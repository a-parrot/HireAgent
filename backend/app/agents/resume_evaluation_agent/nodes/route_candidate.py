"""Compute the total and threshold route using configured rules and evidence."""

from app.agents.resume_evaluation_agent.decision import summarize


async def run(runtime, state):
    return {
        "summary": summarize(
            await runtime.rules(state["candidate_id"]),
            state["pages"],
            state["analysis"],
            state["evaluation"],
            state.get(
                "verification", {"needs_human_review": False, "review_notes": []}
            ),
        )
    }


def save(candidate, output, config):
    for key, value in output["summary"].items():
        setattr(candidate, key, value)
    candidate.processing_status = "running"
