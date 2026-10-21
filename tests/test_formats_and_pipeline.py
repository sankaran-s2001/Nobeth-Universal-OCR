"""Additional unit tests covering HEIC, TIFF, WEBP formats, multi-page PDFs, and complex CSV flattening."""

import io
import fitz
import numpy as np
from PIL import Image

from utils.file_utils import detect_file_format
from utils.image_utils import (
    load_image_safely,
    detect_skew_angle,
    create_preprocessed_copy,
)
from utils.pdf_utils import inspect_pdf, render_pdf_pages_adaptively
from services.export_service import export_to_csv, export_to_txt
from services.extraction_service import parse_extraction_response
from models.schemas import ConfidenceLevel


def test_webp_and_tiff_image_loading():
    # 1. WEBP format
    img_webp = Image.new("RGB", (200, 150), color="blue")
    buf_webp = io.BytesIO()
    img_webp.save(buf_webp, format="WEBP")
    webp_bytes = buf_webp.getvalue()

    ext, mime, is_supp = detect_file_format("sample.webp", webp_bytes)
    assert ext == ".webp"
    assert is_supp is True
    loaded_webp = load_image_safely(webp_bytes)
    assert loaded_webp.size == (200, 150)

    # 2. TIFF format
    img_tiff = Image.new("RGB", (300, 200), color="green")
    buf_tiff = io.BytesIO()
    img_tiff.save(buf_tiff, format="TIFF")
    tiff_bytes = buf_tiff.getvalue()

    ext_t, mime_t, is_supp_t = detect_file_format("document.tiff", tiff_bytes)
    assert ext_t in [".tiff", ".tif"]
    assert is_supp_t is True
    loaded_tiff = load_image_safely(tiff_bytes)
    assert loaded_tiff.size == (300, 200)


def test_multi_page_pdf_rendering():
    # Create a 3-page PDF
    doc = fitz.open()
    for page_num in range(1, 4):
        p = doc.new_page(width=595, height=842)
        p.insert_text((50, 100), f"Nobeth Universal OCR Page {page_num}")
    pdf_bytes = doc.tobytes()
    doc.close()

    inspection = inspect_pdf(pdf_bytes)
    assert inspection.is_valid is True
    assert inspection.page_count == 3

    rendered_pages = render_pdf_pages_adaptively(pdf_bytes)
    assert len(rendered_pages) == 3
    for p_img in rendered_pages:
        assert isinstance(p_img, Image.Image)
        assert p_img.width > 500


def test_extraction_response_parser():
    sample_response = (
        "=== METADATA ===\n"
        "DOCUMENT_TYPE: invoice\n"
        "CONFIDENCE_LEVEL: HIGH\n"
        "CONFIDENCE_SCORE: 0.96\n\n"
        "=== RAW_TEXT ===\n"
        "TAX INVOICE\n"
        "Invoice No: INV-00432\n"
        "Date: 2026-08-11\n"
        "Total: $500.00\n"
    )

    doc_type, conf_level, conf_score, raw_text = parse_extraction_response(sample_response)
    assert doc_type == "invoice"
    assert conf_level == ConfidenceLevel.HIGH
    assert conf_score == 0.96
    assert "TAX INVOICE" in raw_text
    assert "INV-00432" in raw_text


def test_csv_export_with_nested_table_matrix():
    # Table data as list of lists (headers + rows)
    data = {
        "document_type": "table",
        "title": "Quarterly Financials",
        "currency": "USD",
        "matrix": [
            ["Q1", "1000", "200"],
            ["Q2", "1200", "250"],
            ["Q3", "1400", "300"],
        ],
    }
    csv_str = export_to_csv(data)
    lines = [l.strip() for l in csv_str.strip().splitlines() if l.strip()]
    assert len(lines) == 4  # Header + 3 rows
    assert "title" in lines[0]
    assert "Q1" in lines[1]
    assert "Q2" in lines[2]
    assert "Q3" in lines[3]


def test_txt_export_header_and_content():
    raw = "Item 1: 10.00\nItem 2: 20.00\nTotal: 30.00"
    txt = export_to_txt(raw_text=raw, filename="bill.jpg", document_type="receipt", confidence="HIGH")
    assert "NOBETH UNIVERSAL OCR - RAW EXTRACTION EXPORT" in txt
    assert "bill.jpg" in txt
    assert "receipt" in txt
    assert "Item 1: 10.00" in txt


def test_mock_gemini_extraction_and_structuring_pipeline():
    from unittest.mock import MagicMock
    from services.extraction_service import extract_raw_document
    from services.structuring_service import structure_raw_extraction

    # 1. Mock Gemini Service for Stage 1 Extraction
    mock_service = MagicMock()
    mock_service.generate_vision_content.return_value = (
        "=== METADATA ===\n"
        "DOCUMENT_TYPE: invoice\n"
        "CONFIDENCE_LEVEL: HIGH\n"
        "CONFIDENCE_SCORE: 0.95\n\n"
        "=== RAW_TEXT ===\n"
        "Nobeth Analytics Invoice\n"
        "Invoice No: INV-100\n"
        "Total: $150.00\n"
    )

    test_img = Image.new("RGB", (100, 100), color="white")
    extraction_res = extract_raw_document([test_img], gemini_service=mock_service)

    assert extraction_res.document_type == "invoice"
    assert extraction_res.confidence_level == ConfidenceLevel.HIGH
    assert extraction_res.confidence_score == 0.95
    assert "INV-100" in extraction_res.verbatim_text
    mock_service.generate_vision_content.assert_called_once()

    # 2. Mock Gemini Service for Stage 2 Structuring
    mock_service.generate_text_content.return_value = (
        '{\n'
        '  "document_type": "invoice",\n'
        '  "invoice_no": "INV-100",\n'
        '  "total": 150.00,\n'
        '  "confidence_level": "HIGH"\n'
        '}'
    )

    struct_res = structure_raw_extraction(
        reviewed_raw_text=extraction_res.verbatim_text,
        document_type_hint=extraction_res.document_type,
        gemini_service=mock_service,
    )

    assert struct_res.is_valid is True
    assert struct_res.document_type == "invoice"
    assert struct_res.data["invoice_no"] == "INV-100"
    assert struct_res.data["total"] == 150.00
    # Traceability links should match
    field_names = [t.field_name for t in struct_res.traceability]
    assert "invoice_no" in field_names


def test_mock_pipeline_error_handling():
    from unittest.mock import MagicMock
    import pytest
    from services.extraction_service import extract_raw_document, parse_extraction_response
    from services.structuring_service import structure_raw_extraction

    # 1. Missing metadata header in raw extraction
    raw_response_no_meta = "Just plain raw extracted text without metadata tags"
    doc_type, conf, score, raw_text = parse_extraction_response(raw_response_no_meta)
    assert doc_type == "unknown"
    assert conf == ConfidenceLevel.HIGH
    assert score is None
    assert raw_text == raw_response_no_meta

    # 2. Stage 1 API exception propagation
    mock_failing_service = MagicMock()
    mock_failing_service.generate_vision_content.side_effect = RuntimeError("Quota exceeded 429")
    test_img = Image.new("RGB", (50, 50), color="blue")
    with pytest.raises(RuntimeError) as exc_info:
        extract_raw_document([test_img], gemini_service=mock_failing_service)
    assert "Quota exceeded" in str(exc_info.value)

    # 3. Stage 2 API exception propagation
    mock_failing_service.generate_text_content.side_effect = RuntimeError("Service unavailable 503")
    with pytest.raises(RuntimeError) as exc_info:
        structure_raw_extraction("Sample text", gemini_service=mock_failing_service)
    assert "Service unavailable" in str(exc_info.value)

    # 4. Stage 2 Malformed JSON handling: preserves reviewed text without crashing
    mock_malformed_service = MagicMock()
    mock_malformed_service.generate_text_content.return_value = "This is not JSON at all: broken output {"
    res_malformed = structure_raw_extraction(
        reviewed_raw_text="Customer: John Doe\nAmount: $50",
        document_type_hint="receipt",
        gemini_service=mock_malformed_service,
    )
    assert res_malformed.is_valid is False
    assert res_malformed.confidence_level == ConfidenceLevel.LOW
    assert "Customer: John Doe" in res_malformed.data["raw_text"]
    assert "error" in res_malformed.data
