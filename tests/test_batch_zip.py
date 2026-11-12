"""
Unit tests for Batch ZIP Archive generation, manifest serialization, and official Nobeth Analytics logo asset.
"""

import json
import os
import tempfile
import zipfile
from datetime import datetime
from PIL import Image
import pytest

from models.batch_schemas import BatchItemResult, BatchItemStatus, BatchJobSummary
from services.batch_archive_service import (
    build_batch_zip_archive,
    generate_batch_readme,
    generate_batch_zip_filename,
    generate_manifest_csv,
    generate_manifest_json,
    sanitize_filename_stem,
)
from ui.components import get_nobeth_logo_base64, render_header


def test_sanitize_filename_stem():
    assert sanitize_filename_stem("receipt #001 (Store).jpg") == "receipt_001_Store"
    assert sanitize_filename_stem("invoice_2026.png") == "invoice_2026"
    assert sanitize_filename_stem("../../../etc/passwd.jpg") == "passwd"
    assert sanitize_filename_stem("   ") == "document"


def test_generate_batch_zip_filename():
    dt = datetime(2026, 11, 12, 10, 30)
    name = generate_batch_zip_filename("BAT-A1B2", 50, dt)
    assert name == "Nobeth_OCR_Batch_2026-11-12_50_files_BATA1B2.zip"


def test_manifest_json_sanitization_and_structure():
    summary = BatchJobSummary(
        batch_id="BAT-TEST01",
        batch_started_at="2026-11-12 10:00:00",
        batch_finished_at="2026-11-12 10:05:00",
        total_files=2,
        valid_count=2,
        completed_count=2,
        success_count=2,
        total_duration=12.5,
        average_duration_per_item=6.25,
    )
    items = [
        BatchItemResult(
            file_index=1,
            original_filename="receipt_1.jpg",
            status=BatchItemStatus.SUCCESS,
            document_type="receipt",
            confidence="HIGH",
            model_used="gemini-3.1-flash-lite",
            total_duration=6.1,
            ocr_duration=3.5,
            structuring_duration=2.5,
            json_filename="receipt_1.json",
            csv_filename="receipt_1.csv",
            txt_filename="receipt_1.txt",
        ),
        BatchItemResult(
            file_index=2,
            original_filename="invoice_2.png",
            status=BatchItemStatus.SUCCESS,
            document_type="invoice",
            confidence="HIGH",
            model_used="gemini-3.5-flash-lite",
            total_duration=6.4,
            ocr_duration=3.8,
            structuring_duration=2.4,
            json_filename="invoice_2.json",
            csv_filename="invoice_2.csv",
            txt_filename="invoice_2.txt",
        ),
    ]

    manifest_json_str = generate_manifest_json(summary, items)
    parsed = json.loads(manifest_json_str)

    assert parsed["batch_id"] == "BAT-TEST01"
    assert parsed["summary"]["total_files"] == 2
    assert len(parsed["records"]) == 2
    assert parsed["records"][0]["original_filename"] == "receipt_1.jpg"
    assert parsed["records"][0]["model_used"] == "gemini-3.1-flash-lite"
    # Ensure no raw text or api keys leaked
    assert "api_key" not in manifest_json_str
    assert "AQ." not in manifest_json_str


def test_manifest_csv_structure():
    summary = BatchJobSummary(
        batch_id="BAT-TEST01",
        batch_started_at="2026-11-12 10:00:00",
        total_files=1,
    )
    items = [
        BatchItemResult(
            file_index=1,
            original_filename="receipt_1.jpg",
            status=BatchItemStatus.SUCCESS,
            document_type="receipt",
            confidence="HIGH",
            total_duration=5.2,
        ),
    ]
    csv_str = generate_manifest_csv(summary, items)
    lines = csv_str.strip().splitlines()
    assert len(lines) == 2  # header + 1 row
    assert "Batch ID" in lines[0]
    assert "BAT-TEST01" in lines[1]
    assert "receipt_1.jpg" in lines[1]


def test_build_batch_zip_archive_structure(tmp_path):
    summary = BatchJobSummary(
        batch_id="BAT-ZIPTEST",
        batch_started_at="2026-11-12 10:00:00",
        batch_finished_at="2026-11-12 10:02:00",
        total_files=3,
        valid_count=3,
        completed_count=3,
        success_count=1,
        partial_count=1,
        failed_count=1,
        total_duration=15.0,
    )

    items = [
        # Successful item with JSON, CSV, TXT
        BatchItemResult(
            file_index=1,
            original_filename="receipt_01.jpg",
            status=BatchItemStatus.SUCCESS,
            output_basename="receipt_01",
            json_content='{"merchant": "Store A", "total": 10.0}',
            csv_content='merchant,total\nStore A,10.0\n',
            txt_content='Store A\nTotal: 10.0',
            total_duration=4.5,
        ),
        # Partial item with preserved TXT
        BatchItemResult(
            file_index=2,
            original_filename="receipt_02.png",
            status=BatchItemStatus.PARTIAL,
            output_basename="receipt_02",
            txt_content='Preserved Stage 1 raw text',
            failed_stage="JSON_STRUCTURING",
            error_message="LLM malformed response",
            total_duration=3.2,
        ),
        # Failed item
        BatchItemResult(
            file_index=3,
            original_filename="receipt_03_corrupt.png",
            status=BatchItemStatus.FAILED,
            output_basename="receipt_03_corrupt",
            failed_stage="IMAGE_DECODING",
            error_category="CORRUPT_IMAGE",
            error_message="Cannot parse file bytes as image",
            total_duration=0.5,
        ),
    ]

    zip_path, zip_name, zip_size = build_batch_zip_archive(summary, items, output_dir=str(tmp_path))

    assert os.path.exists(zip_path)
    assert zip_size > 0
    assert zip_name.endswith(".zip")

    # Inspect zip contents
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        root_dir = zip_name.rsplit(".", 1)[0]

        # 1. Manifests & README
        assert f"{root_dir}/batch_manifest.json" in namelist
        assert f"{root_dir}/batch_manifest.csv" in namelist
        assert f"{root_dir}/README.txt" in namelist

        # 2. Successful folder contains json, csv, txt
        assert f"{root_dir}/successful/001_receipt_01/receipt_01.json" in namelist
        assert f"{root_dir}/successful/001_receipt_01/receipt_01.csv" in namelist
        assert f"{root_dir}/successful/001_receipt_01/receipt_01.txt" in namelist

        # 3. Partial folder contains preserved txt and structuring error json
        assert f"{root_dir}/partial/002_receipt_02/receipt_02.txt" in namelist
        assert f"{root_dir}/partial/002_receipt_02/receipt_02_structuring_error.json" in namelist

        # 4. Failed folder contains error json and txt
        assert f"{root_dir}/failed/003_receipt_03_corrupt_error.json" in namelist
        assert f"{root_dir}/failed/003_receipt_03_corrupt_error.txt" in namelist

        # Verify content reading
        with zf.open(f"{root_dir}/successful/001_receipt_01/receipt_01.json") as f:
            content = json.loads(f.read().decode("utf-8"))
            assert content["merchant"] == "Store A"


# ==============================================================================
# 4. OFFICIAL NOBETH ANALYTICS BRANDING & LOGO TESTS
# ==============================================================================
def test_nobeth_analytics_logo_asset():
    """
    Verifies that the official Nobeth Analytics logo exists in static/assets/,
    has valid 1:1 aspect ratio, and loads cleanly into the UI header.
    """
    logo_path = os.path.join("static", "assets", "nobeth-analytics.png")
    assert os.path.exists(logo_path), f"Expected logo asset at {logo_path}"

    with Image.open(logo_path) as img:
        width, height = img.size
        assert width > 0 and height > 0
        assert width == height, f"Expected 1:1 aspect ratio, got {width}x{height}"
        assert img.format == "PNG"

    # Verify base64 retrieval
    b64 = get_nobeth_logo_base64()
    assert b64 is not None and len(b64) > 100

    # Verify header renders official logo
    header_html = render_header(
        api_key_configured=True,
        model_id="gemini-3.1-flash-lite",
        stage="EMPTY",
    )
    assert 'class="nobeth-official-logo"' in header_html
    assert 'src="data:image/png;base64,' in header_html


def test_build_batch_zip_archive_with_reviewed_item(tmp_path):
    """
    Verifies that items with status SUCCESS_REVIEWED are stored under successful/
    with updated JSON, CSV, and TXT outputs, and reflected in the manifest.
    """
    summary = BatchJobSummary(
        batch_id="BAT-REVIEWTEST",
        batch_started_at="2026-11-12 10:00:00",
        batch_finished_at="2026-11-12 10:03:00",
        total_files=1,
        valid_count=1,
        completed_count=1,
        success_count=1,
        total_duration=5.0,
    )
    items = [
        BatchItemResult(
            file_index=1,
            original_filename="receipt_reviewed.jpg",
            status=BatchItemStatus.SUCCESS_REVIEWED,
            is_reviewed=True,
            review_count=1,
            output_basename="receipt_reviewed",
            json_content='{"merchant": "Store Reviewed", "total": 99.0}',
            csv_content='merchant,total\nStore Reviewed,99.0\n',
            txt_content='Store Reviewed\nTotal: 99.0',
            total_duration=5.0,
        )
    ]

    zip_path, zip_name, zip_size = build_batch_zip_archive(summary, items, output_dir=str(tmp_path))
    assert os.path.exists(zip_path)
    assert zip_size > 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        root_dir = zip_name.rsplit(".", 1)[0]
        assert f"{root_dir}/successful/001_receipt_reviewed/receipt_reviewed.json" in namelist
        assert f"{root_dir}/successful/001_receipt_reviewed/receipt_reviewed.csv" in namelist
        assert f"{root_dir}/successful/001_receipt_reviewed/receipt_reviewed.txt" in namelist

        with zf.open(f"{root_dir}/batch_manifest.json") as f:
            manifest = json.loads(f.read().decode("utf-8"))
            rec = manifest["records"][0]
            assert rec["status"] == "SUCCESS_REVIEWED"
            assert rec["is_reviewed"] is True
            assert rec["review_count"] == 1


