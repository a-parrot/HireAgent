"""Hiring orchestration: evaluate once, review only exceptions, then schedule."""

from functools import partial
from itertools import pairwise

from langgraph.graph import END, START, StateGraph

from app.agents.recruitment_agent.nodes import human_review
from app.agents.recruitment_agent.recruitment_state import RecruitmentState
from app.agents.resume_evaluation_agent.scoring import FLOW_VERSION, LEGACY_FLOW_VERSION


def build_graph(runtime, checkpointer):
    graph = StateGraph(RecruitmentState)
    sequence = ["parse_pdf", "analyze_resume", "evaluate_candidate", "route_candidate"]
    for name in [
        *sequence,
        "review_evaluation",
        "summarize_result",
        "auto_approve",
        "screen_hard_conditions",
        "extract_scoring_evidence",
        "calculate_score",
        "verify_hard_conditions",
        "verify_scoring_evidence",
    ]:

        async def step(state, node=name):
            return await runtime.execute_node(node, state)

        graph.add_node(name, step)
    graph.add_node("human_review", partial(human_review.run, runtime))
    graph.add_edge(START, sequence[0])
    for left, right in pairwise(sequence[1:]):
        graph.add_edge(left, right)

    async def select_flow(state):
        rules = await runtime.rules(state["candidate_id"])
        return (
            "screen_hard_conditions"
            if rules.get("evaluation_flow") in (FLOW_VERSION, LEGACY_FLOW_VERSION)
            else "analyze_resume"
        )

    graph.add_conditional_edges(
        "parse_pdf", select_flow, ["screen_hard_conditions", "analyze_resume"]
    )

    async def after_screen(state):
        rules = await runtime.rules(state["candidate_id"])
        if rules.get("evaluation_flow") == FLOW_VERSION:
            return "verify_hard_conditions"
        return (
            END
            if state["screening"]["result"] == "unsatisfied"
            else "extract_scoring_evidence"
        )

    graph.add_conditional_edges(
        "screen_hard_conditions",
        after_screen,
        ["verify_hard_conditions", "extract_scoring_evidence", END],
    )
    graph.add_conditional_edges(
        "verify_hard_conditions",
        lambda state: (
            END
            if state["screening"]["result"] == "unsatisfied"
            else "extract_scoring_evidence"
        ),
        [END, "extract_scoring_evidence"],
    )

    async def after_scoring(state):
        rules = await runtime.rules(state["candidate_id"])
        return (
            "verify_scoring_evidence"
            if rules.get("evaluation_flow") == FLOW_VERSION
            else "calculate_score"
        )

    graph.add_conditional_edges(
        "extract_scoring_evidence",
        after_scoring,
        ["verify_scoring_evidence", "calculate_score"],
    )
    graph.add_edge("verify_scoring_evidence", "calculate_score")
    graph.add_conditional_edges(
        "calculate_score",
        lambda state: {
            "recommended": "auto_approve",
            "needs_review": "human_review",
            "deferred": END,
        }[state["summary"]["recommendation"]],
        ["auto_approve", "human_review", END],
    )
    graph.add_conditional_edges(
        "route_candidate",
        lambda state: {
            "recommended": "auto_approve",
            "needs_review": "review_evaluation",
            "deferred": END,
        }[state["summary"]["recommendation"]],
    )
    graph.add_edge("review_evaluation", "summarize_result")
    graph.add_edge("summarize_result", "human_review")
    graph.add_edge("auto_approve", END)
    graph.add_edge("human_review", END)
    return graph.compile(checkpointer=checkpointer)
