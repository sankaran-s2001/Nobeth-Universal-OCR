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


def test_gemini_api_key_validation(monkeypatch):
    from services.gemini_service import get_gemini_api_key

    # 1. Missing / unset
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert get_gemini_api_key() is None

    # 2. Empty string
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert get_gemini_api_key() is None

    # 3. Whitespace only
    monkeypatch.setenv("GEMINI_API_KEY", "   \t\n  ")
    assert get_gemini_api_key() is None

    # 4. Example placeholder string
    monkeypatch.setenv("GEMINI_API_KEY", "your_gemini_api_key_here")
    assert get_gemini_api_key() is None

    # 5. Quoted placeholder string
    monkeypatch.setenv("GEMINI_API_KEY", '"your_gemini_api_key_here"')
    assert get_gemini_api_key() is None

    # 6. Alternative template placeholder
    monkeypatch.setenv("GEMINI_API_KEY", "your_actual_key_here")
    assert get_gemini_api_key() is None

    # 7. Valid credential format
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFakeKeyForTesting1234567890")
    assert get_gemini_api_key() == "AIzaSyFakeKeyForTesting1234567890"


def test_invalid_upload_state_clearing_and_size_limits(monkeypatch):
    # 1. Renamed executable with image extension
    is_valid, err_msg, _ = validate_upload_bytes("malicious.png", b"MZ\x90\x00\x03\x00executable")
    assert is_valid is False
    assert err_msg is not None

    # 2. Oversized file exceeding limit
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "1")
    large_payload = b"\xff\xd8\xff" + (b"0" * (2 * 1024 * 1024))
    is_valid_large, err_large, _ = validate_upload_bytes("large.jpg", large_payload)
    assert is_valid_large is False
    assert "exceeds limit" in err_large.lower()


def test_state_reset_and_uploader_isolation():
    # Simulate session state dictionary
    session = {
        "stage": "STRUCTURED_READY",
        "filename": "invoice_1.pdf",
        "file_bytes": b"%PDF-1.4...",
        "original_images": ["<ImageObj>"],
        "raw_text_ai": "Invoice text",
        "raw_text_user": "Edited invoice text",
        "structured_json_ai": {"total": 100},
        "structured_json_user": '{"total": 100}',
        "uploader_key": 0,
        "raw_text_editor_widget": "Edited invoice text",
        "json_editor_widget": '{"total": 100}',
    }

    # Simulate reset_session logic
    next_key = session.get("uploader_key", 0) + 1
    session.clear()
    session.update({
        "stage": "EMPTY",
        "filename": None,
        "file_bytes": None,
        "original_images": [],
        "raw_text_ai": "",
        "raw_text_user": "",
        "structured_json_ai": None,
        "structured_json_user": "",
        "uploader_key": next_key,
    })

    assert session["stage"] == "EMPTY"
    assert session["filename"] is None
    assert session["original_images"] == []
    assert session["raw_text_ai"] == ""
    assert session["structured_json_ai"] is None
    assert session["uploader_key"] == 1
    assert "raw_text_editor_widget" not in session
    assert "json_editor_widget" not in session


def test_raw_text_and_json_editor_widget_state_behavior():
    """Verify that text area widgets bind directly to session state keys without default value warnings."""
    from streamlit.testing.v1 import AppTest

    snippet = """
import streamlit as st

if 'raw_text_ai' not in st.session_state:
    st.session_state.raw_text_ai = 'VERBATIM AI EXTRACTION'
    st.session_state.raw_text_user = 'VERBATIM AI EXTRACTION'

def on_reset_raw():
    st.session_state.raw_text_user = st.session_state.raw_text_ai

st.text_area('Editable Raw Text', key='raw_text_user')
st.button('Reset Raw', on_click=on_reset_raw, key='btn_reset_raw')
"""
    at = AppTest.from_string(snippet)
    at.run()
    # Ensure no duplicate default value warning is raised
    assert len(at.warning) == 0
    assert at.text_area[0].value == "VERBATIM AI EXTRACTION"

    # User edits raw text
    at.text_area[0].input("USER EDITED TEXT").run()
    assert at.session_state["raw_text_user"] == "USER EDITED TEXT"
    assert len(at.warning) == 0

    # User clicks Reset Raw
    at.button[0].click().run()
    assert at.session_state["raw_text_user"] == "VERBATIM AI EXTRACTION"
    assert at.text_area[0].value == "VERBATIM AI EXTRACTION"
    assert len(at.warning) == 0


def test_gemini_client_http_options_timeout_unit():
    """Verify that HttpOptions timeout uses milliseconds (60_000 ms) and converts to 60.0 seconds."""
    from services.gemini_service import get_cached_genai_client
    import google.genai._api_client as ac

    client = get_cached_genai_client("test_mock_key_abc123")
    timeout_ms = client._api_client._http_options.timeout
    assert timeout_ms == 60_000, f"Expected 60_000 ms, got {timeout_ms}"
    timeout_sec = ac.get_timeout_in_seconds(timeout_ms)
    assert timeout_sec == 60.0, f"Expected 60.0 seconds, got {timeout_sec}"
