"""Local PDF text extraction. No network, page markers or page index output."""

import asyncio
from pathlib import Path

import pymupdf

from app.core.errors import BusinessError


class PDFClient:
    version = pymupdf.VersionBind

    async def extract(self, path: Path) -> str:
        return await asyncio.to_thread(self._extract, path)

    @staticmethod
    def _extract(path: Path) -> str:
        try:
            with pymupdf.open(path) as document:
                if document.needs_pass:
                    raise BusinessError("PDF 已加密，请上传可直接读取的 PDF")
                text = "\n\n".join(
                    part
                    for page in document
                    if (part := page.get_text("text", sort=True).strip())
                )
        except (OSError, RuntimeError, ValueError):
            raise BusinessError("PDF 无法读取，请检查文件是否损坏") from None
        if not text.strip():
            raise BusinessError("PDF 未提取到可读文本，扫描件请先完成 OCR 后重新上传")
        return text
