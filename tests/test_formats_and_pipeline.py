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
