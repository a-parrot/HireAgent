from typing import TypedDict


class ImportState(TypedDict, total=False):
    file_id: int
    task_id: int
    file_type: str
    pages: list[dict]
