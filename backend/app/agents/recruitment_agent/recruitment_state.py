from typing import Any, TypedDict


class RecruitmentState(TypedDict, total=False):
    candidate_id: int
    pages: list[dict[str, Any]]
    analysis: dict[str, Any]
    evaluation: dict[str, Any]
    verification: dict[str, Any]
    summary: dict[str, Any]
    decision: str
