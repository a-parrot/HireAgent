"""Ensure a complete text artifact exists before completing the import."""

from app.core.errors import BusinessError
from app.models.mysql.entities import File
from app.repositories.common import require


async def run(runtime, state):
    async with runtime.db.session() as session:
        file = await require(session, File, state["file_id"])
        if not file.normalized_markdown_path:
            raise BusinessError("PDF 未生成解析正文，不能标记完成")
    return {}
