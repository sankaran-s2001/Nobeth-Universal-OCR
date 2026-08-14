"""Unit tests for format detection, file validation, and resilient JSON parsing."""

import io
import fitz
from PIL import Image

from utils.file_utils import detect_file_format, validate_file_size
from utils.pdf_utils import inspect_pdf
from utils.validation import parse_and_validate_json, validate_upload_bytes


def test_file_format_detection_and_validation():
    # 1. Valid JPEG bytes
    img = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpg_bytes = buf.getvalue()

    is_valid, err, ext = validate_upload_bytes("test_doc.jpg", jpg_bytes)
    assert is_valid is True
    assert err is None
    assert ext in [".jpg", ".jpeg"]

    # 2. Unsupported format (.exe)
    is_valid_exe, err_exe, ext_exe = validate_upload_bytes("malicious.exe", b"MZ\x90\x00\x03\x00")
    assert is_valid_exe is False
    assert "Unsupported file format" in err_exe

    # 3. Empty file (0 bytes)
    is_valid_empty, err_empty, _ = validate_upload_bytes("empty.png", b"")
    assert is_valid_empty is False
    assert "empty" in err_empty.lower()


def test_pdf_inspection_valid_and_corrupt():
    # 1. Generate valid minimal PDF with PyMuPDF
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), "Nobeth Universal OCR Test PDF")
    pdf_bytes = doc.tobytes()
    doc.close()

    inspection = inspect_pdf(pdf_bytes)
    assert inspection.is_valid is True
    assert inspection.page_count == 1
    assert inspection.is_encrypted is False

    # 2. Corrupted PDF bytes
    corrupt_inspection = inspect_pdf(b"%PDF-1.4 corrupt data garbage string")
    assert corrupt_inspection.is_valid is False
    assert "corrupted" in corrupt_inspection.error_message.lower()


def test_json_parser_and_repair():
    # 1. Clean JSON
    clean_json = '{"document_type": "invoice", "total": 1250.00}'
    data, is_valid, _ = parse_and_validate_json(clean_json)
    assert is_valid is True
    assert data["document_type"] == "invoice"
    assert data["total"] == 1250.00

    # 2. Markdown-wrapped JSON
    md_json = "```json\n{\n  \"document_type\": \"receipt\",\n  \"total\": 50.0\n}\n```"
    data_md, is_valid_md, _ = parse_and_validate_json(md_json)
    assert is_valid_md is True
    assert data_md["document_type"] == "receipt"

    # 3. JSON with trailing commas (auto-repair)
    trailing_comma_json = '{"merchant": "Corner Store", "items": ["Milk", "Bread",], "tax": null,}'
    data_repaired, is_valid_repaired, _ = parse_and_validate_json(trailing_comma_json)
    assert is_valid_repaired is True
    assert data_repaired["merchant"] == "Corner Store"
    assert len(data_repaired["items"]) == 2

    # 4. Completely invalid gibberish string
    data_bad, is_valid_bad, err_msg = parse_and_validate_json("not a json at all")
    assert is_valid_bad is False
    assert data_bad is None
    assert "Invalid JSON" in err_msg or "Failed" in err_msg
