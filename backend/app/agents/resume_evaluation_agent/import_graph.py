"""File import workflow; never calls a language model."""

from langgraph.graph import END, START, StateGraph

from app.agents.resume_evaluation_agent.import_state import ImportState


def build_import_graph(runtime):
    graph = StateGraph(ImportState)
    for name in ("prepare_import", "parse_pdf", "save_import_result"):

        async def step(state, node=name):
            return await runtime.execute(node, state)

        graph.add_node(name, step)
    graph.add_edge(START, "prepare_import")
    graph.add_edge("prepare_import", "parse_pdf")
    graph.add_edge("parse_pdf", "save_import_result")
    graph.add_edge("save_import_result", END)
    return graph.compile()
