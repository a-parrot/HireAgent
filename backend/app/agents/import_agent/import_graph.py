"""File import workflow; never calls a language model."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class ImportState(TypedDict, total=False):
    file_id: int
    task_id: int
    file_type: str
    pages: list[dict]


def build_import_graph(runtime):
    graph = StateGraph(ImportState)
    for name in (
        "prepare_import",
        "parse_pdf",
        "parse_word",
        "normalize_content",
        "save_import_result",
    ):

        async def step(state, node=name):
            return await runtime.execute(node, state)

        graph.add_node(name, step)
    graph.add_edge(START, "prepare_import")
    graph.add_conditional_edges(
        "prepare_import",
        lambda s: "parse_word" if s["file_type"] == "docx" else "parse_pdf",
    )
    graph.add_edge("parse_pdf", "normalize_content")
    graph.add_edge("parse_word", "normalize_content")
    graph.add_edge("normalize_content", "save_import_result")
    graph.add_edge("save_import_result", END)
    return graph.compile()
