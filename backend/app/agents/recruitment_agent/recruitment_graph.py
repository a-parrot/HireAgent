from itertools import pairwise

from langgraph.graph import END, START, StateGraph

from app.agents.recruitment_agent.recruitment_state import RecruitmentState


def build_graph(runtime, checkpointer):
    graph = StateGraph(RecruitmentState)
    sequence = [
        "parse_pdf",
        "analyze_resume",
        "evaluate_candidate",
        "review_evaluation",
        "summarize_result",
    ]
    for name in sequence:

        async def step(state, node=name):
            return await runtime.execute_node(node, state)

        graph.add_node(name, step)
    graph.add_node("human_review", runtime.human_review)
    graph.add_edge(START, sequence[0])
    for left, right in pairwise(sequence):
        graph.add_edge(left, right)
    graph.add_conditional_edges(
        sequence[-1],
        lambda state: (
            "human_review" if state["summary"]["recommendation"] != "deferred" else END
        ),
    )
    graph.add_edge("human_review", END)
    return graph.compile(checkpointer=checkpointer)
