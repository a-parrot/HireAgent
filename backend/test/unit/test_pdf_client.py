import pymupdf
import pytest

from app.clients.pdf_client import PDFClient
from app.core.errors import BusinessError


@pytest.mark.asyncio
async def test_merges_all_pages_without_page_markers(tmp_path):
    path = tmp_path / "resume.pdf"
    with pymupdf.open() as doc:
        for text in ["Work experience", "Project achievements"]:
            doc.new_page().insert_text((72, 72), text)
        doc.save(path)
    result = await PDFClient().extract(path)
    assert result == "Work experience\n\nProject achievements"
    assert "page_no" not in result


@pytest.mark.asyncio
async def test_image_only_or_empty_pdf_reports_ocr_needed(tmp_path):
    path = tmp_path / "scan.pdf"
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(path)
    with pytest.raises(BusinessError, match="OCR"):
        await PDFClient().extract(path)


@pytest.mark.asyncio
async def test_encrypted_and_corrupt_pdf_have_safe_errors(tmp_path):
    path = tmp_path / "encrypted.pdf"
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 72), "Private")
        doc.save(
            path,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="test",
            user_pw="test",
        )
    with pytest.raises(BusinessError, match="加密"):
        await PDFClient().extract(path)
    path.write_bytes(b"%PDF-invalid")
    with pytest.raises(BusinessError, match="无法读取"):
        await PDFClient().extract(path)
