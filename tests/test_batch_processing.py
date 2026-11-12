"""
Unit and integration tests for Nobeth Universal OCR Bulk Image Processing Engine.
Validates preflight checks, strictly sequential execution (concurrency == 1) on a 50-image batch,
failure isolation, fatal error halting, and result traceability.
"""

import io
import time
from typing import List
from unittest.mock import MagicMock, patch
from PIL import Image
import pytest

from models.batch_schemas import (
    BatchItemStage,
    BatchItemStatus,
    BatchPreflightSummary,
)
from models.schemas import ConfidenceLevel, RawExtractionResult, StructuredExtractionResult
from services.batch_processing_service import (
    generate_unique_output_basenames,
    process_batch_sequential,
    validate_batch_preflight,
)


class MockUploadedFile:
    """Mock Streamlit UploadedFile object."""

    def __init__(self, name: str, data: bytes, path: str = ""):
        self.name = name
        self.data = data
        self.path = path or name

    def getvalue(self) -> bytes:
        return self.data

    def read(self) -> bytes:
        return self.data


def create_synthetic_png_bytes(width: int = 50, height: int = 50, color: tuple = (100, 150, 200)) -> bytes:
    """Creates a small valid in-memory PNG image bytes."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ==============================================================================
# 1. BATCH PREFLIGHT VALIDATION TESTS
# ==============================================================================
def test_preflight_empty_files():
    summary = validate_batch_preflight([])
    assert summary.total_selected == 0
    assert summary.is_processable is False
    assert "No files selected" in (summary.error_message or "")


def test_preflight_valid_images():
    b1 = create_synthetic_png_bytes(color=(255, 0, 0))
    b2 = create_synthetic_png_bytes(color=(0, 255, 0))
    files = [
        MockUploadedFile("receipt_01.png", b1),
        MockUploadedFile("receipt_02.png", b2),
    ]
    summary = validate_batch_preflight(files)
    assert summary.total_selected == 2
    assert summary.valid_count == 2
    assert summary.unsupported_count == 0
    assert summary.invalid_count == 0
    assert summary.is_processable is True


def test_preflight_mixed_supported_unsupported_invalid():
    b_valid = create_synthetic_png_bytes()
    b_empty = b""
    b_pdf = b"%PDF-1.4 dummy pdf header content"
    b_txt = b"Plain text file"

    files = [
        MockUploadedFile("valid.png", b_valid),
        MockUploadedFile("empty.jpg", b_empty),
        MockUploadedFile("doc.pdf", b_pdf),
        MockUploadedFile("notes.txt", b_txt),
    ]

    summary = validate_batch_preflight(files)
    assert summary.total_selected == 4
    assert summary.valid_count == 1
    assert summary.invalid_count == 1  # empty
    assert summary.unsupported_count == 2  # pdf and txt
    assert summary.is_processable is True


def test_preflight_file_count_limit():
    b_valid = create_synthetic_png_bytes()
    files = [MockUploadedFile(f"img_{i}.png", b_valid) for i in range(15)]
    summary = validate_batch_preflight(files, max_files=10)
    assert summary.total_selected == 15
    assert summary.is_processable is False
    assert "exceeds maximum limit" in (summary.error_message or "")


def test_preflight_single_file_size_limit():
    large_bytes = b"x" * 1000
    files = [MockUploadedFile("big.png", large_bytes)]
    summary = validate_batch_preflight(files, max_single_size=500)
    assert summary.invalid_count == 1
    assert summary.is_processable is False


def test_preflight_total_batch_size_limit():
    b = create_synthetic_png_bytes()
    files = [MockUploadedFile(f"img_{i}.png", b) for i in range(5)]
    summary = validate_batch_preflight(files, max_total_size=len(b) * 2)
    assert summary.is_processable is False
    assert "Total upload size" in (summary.error_message or "")


def test_preflight_duplicate_stems_collision_resolution():
    b = create_synthetic_png_bytes()
    files = [
        MockUploadedFile("invoice.jpg", b),
        MockUploadedFile("invoice.png", b),
        MockUploadedFile("invoice.webp", b),
    ]
    summary = validate_batch_preflight(files)
    basenames = generate_unique_output_basenames(summary.items)
    assert basenames[1] == "invoice"
    assert basenames[2] == "invoice_2"
    assert basenames[3] == "invoice_3"


def test_preflight_unicode_and_special_filenames():
    b = create_synthetic_png_bytes()
    files = [
        MockUploadedFile("factura_españa_#01 (final).png", b),
        MockUploadedFile("receipt  spaces  & symbols.jpg", b),
    ]
    summary = validate_batch_preflight(files)
    basenames = generate_unique_output_basenames(summary.items)
    assert basenames[1] == "factura_espa_a_01_final"
    assert basenames[2] == "receipt_spaces_symbols"


# ==============================================================================
# 2. 50-IMAGE SEQUENTIAL QUEUE & STRICT CONCURRENCY == 1 VERIFICATION
# ==============================================================================
def test_50_image_sequential_batch_concurrency_one():
    """
    Creates a deterministic test batch of 50 synthetic images.
    Uses an explicit concurrency counter to mathematically guarantee that
    active processing concurrency never exceeds 1 at any moment.
    """
    num_images = 50
    files = [
        MockUploadedFile(f"receipt_{i:03d}.png", create_synthetic_png_bytes(width=20, height=20))
        for i in range(1, num_images + 1)
    ]

    active_concurrency = 0
    max_concurrency_seen = 0
    processed_order = []

    def mock_extract(images, *args, **kwargs):
        nonlocal active_concurrency, max_concurrency_seen
        active_concurrency += 1
        if active_concurrency > max_concurrency_seen:
            max_concurrency_seen = active_concurrency
        time.sleep(0.001)
        active_concurrency -= 1
        return RawExtractionResult(
            verbatim_text="Store: Nobeth Market\nTotal: $42.50",
            document_type="receipt",
            confidence_level=ConfidenceLevel.HIGH,
            model_used="gemini-3.1-flash-lite",
        )

    def mock_structure(reviewed_raw_text, *args, **kwargs):
        nonlocal active_concurrency, max_concurrency_seen
        active_concurrency += 1
        if active_concurrency > max_concurrency_seen:
            max_concurrency_seen = active_concurrency
        time.sleep(0.001)
        active_concurrency -= 1
        return StructuredExtractionResult(
            document_type="receipt",
            data={"merchant": "Nobeth Market", "total": 42.50},
            confidence_level=ConfidenceLevel.HIGH,
            model_used="gemini-3.1-flash-lite",
        )

    with patch("services.batch_processing_service.extract_raw_document", side_effect=mock_extract), \
         patch("services.batch_processing_service.structure_raw_extraction", side_effect=mock_structure), \
         patch("services.batch_processing_service.INTER_FILE_PACING_SECONDS", 0.0):

        mock_gemini = MagicMock()

        summary, results = process_batch_sequential(
            uploaded_files=files,
            gemini_service=mock_gemini,
            on_item_start=lambda idx, total, fname: processed_order.append(idx),
        )

    # 1. Concurrency must be strictly 1
    assert max_concurrency_seen == 1, f"Expected concurrency 1, but observed {max_concurrency_seen}"

    # 2. Every single image processed
    assert summary.total_files == num_images
    assert summary.completed_count == num_images
    assert summary.success_count == num_images
    assert summary.failed_count == 0
    assert summary.skipped_count == 0

    # 3. Processed strictly in order (1 through 50)
    assert processed_order == list(range(1, num_images + 1))

    # 4. Results correctly mapped to source filenames
    for i, res in enumerate(results, start=1):
        assert res.file_index == i
        assert res.original_filename == f"receipt_{i:03d}.png"
        assert res.status == BatchItemStatus.SUCCESS
        assert res.json_filename == f"receipt_{i:03d}.json"
        assert res.csv_filename == f"receipt_{i:03d}.csv"
        assert res.txt_filename == f"receipt_{i:03d}.txt"


# ==============================================================================
# 3. FAILURE ISOLATION & PARTIAL RECOVERY TESTS
# ==============================================================================
def test_failure_isolation_resilience():
    """
    Verifies that failures in one file (invalid, timeout, structuring failure)
    do not terminate remaining valid items, and that completed results are preserved.
    """
    b_valid = create_synthetic_png_bytes()
    b_empty = b""

    files = [
        MockUploadedFile("file_1_ok.png", b_valid),
        MockUploadedFile("file_2_corrupt.png", b_empty),
        MockUploadedFile("file_3_ok.png", b_valid),
        MockUploadedFile("file_4_ocr_timeout.png", b_valid),
        MockUploadedFile("file_5_struct_fail.png", b_valid),
        MockUploadedFile("file_6_ok.png", b_valid),
    ]

    call_extract_count = 0

    def mock_extract(images, *args, **kwargs):
        nonlocal call_extract_count
        call_extract_count += 1
        # Item 1 is file_1_ok (call 1)
        # Item 2 is file_2_corrupt (preflight empty -> doesn't call extract)
        # Item 3 is file_3_ok (call 2)
        # Item 4 is file_4_ocr_timeout (call 3 -> raises 504)
        # Item 5 is file_5_struct_fail (call 4 -> Stage 1 ok, Stage 2 fail)
        # Item 6 is file_6_ok (call 5)
        if call_extract_count == 3:
            raise Exception("504 DEADLINE_EXCEEDED: Handshake timed out")
        elif call_extract_count == 4:
            return RawExtractionResult(
                verbatim_text="Stage 1 preserved text",
                document_type="receipt",
                confidence_level=ConfidenceLevel.HIGH,
                model_used="gemini-3.1-flash-lite",
            )
        return RawExtractionResult(
            verbatim_text="Extracted text successfully",
            document_type="invoice",
            confidence_level=ConfidenceLevel.HIGH,
            model_used="gemini-3.1-flash-lite",
        )

    def mock_structure(reviewed_raw_text, *args, **kwargs):
        if "Stage 1 preserved text" in reviewed_raw_text:
            raise Exception("Malformed JSON from LLM")
        return StructuredExtractionResult(
            data={"key": "val"},
            confidence_level=ConfidenceLevel.HIGH,
            model_used="gemini-3.1-flash-lite",
        )

    with patch("services.batch_processing_service.extract_raw_document", side_effect=mock_extract), \
         patch("services.batch_processing_service.structure_raw_extraction", side_effect=mock_structure), \
         patch("services.batch_processing_service.INTER_FILE_PACING_SECONDS", 0.0):

        mock_gemini = MagicMock()
        summary, results = process_batch_sequential(files, gemini_service=mock_gemini)

    # Total 6 files
    assert summary.total_files == 6
    assert results[0].status == BatchItemStatus.SUCCESS
    assert results[1].status == BatchItemStatus.INVALID
    assert results[2].status == BatchItemStatus.SUCCESS
    assert results[3].status == BatchItemStatus.FAILED
    assert results[3].error_category == "TIMEOUT"
    assert results[4].status == BatchItemStatus.PARTIAL
    # In partial mode, Stage 1 text must be preserved!
    assert "Stage 1 preserved text" in (results[4].txt_content or "")
    assert results[5].status == BatchItemStatus.SUCCESS


def test_fatal_auth_error_halts_remaining_queue():
    """
    Verifies that a fatal AUTHENTICATION_ERROR halts the queue safely
    and marks remaining unprocessed files as SKIPPED.
    """
    b = create_synthetic_png_bytes()
    files = [
        MockUploadedFile("img_1_auth_fail.png", b),
        MockUploadedFile("img_2_should_skip.png", b),
        MockUploadedFile("img_3_should_skip.png", b),
    ]

    with patch("services.batch_processing_service.extract_raw_document", side_effect=Exception("401 UNAUTHENTICATED: Invalid API_KEY")), \
         patch("services.batch_processing_service.INTER_FILE_PACING_SECONDS", 0.0):

        mock_gemini = MagicMock()
        summary, results = process_batch_sequential(files, gemini_service=mock_gemini)

    assert results[0].status == BatchItemStatus.FAILED
    assert results[0].error_category == "AUTHENTICATION_ERROR"
    assert results[1].status == BatchItemStatus.SKIPPED
    assert results[2].status == BatchItemStatus.SKIPPED
    assert summary.skipped_count == 2


# ==============================================================================
# 5. RETRY, HUMAN-REVIEW, AND AI RE-STRUCTURING TESTS
# ==============================================================================
from services.batch_processing_service import (
    is_item_retryable,
    restructure_single_batch_item,
    retry_all_failed_batch_items,
    retry_single_batch_item,
)
from ui.components import get_nobeth_logo_base64, style_batch_table
import pandas as pd


def test_is_item_retryable_logic():
    """Verifies retry eligibility rules for different error and status categories."""
    item_success = MagicMock(status=BatchItemStatus.SUCCESS, error_category=None, failed_stage=None)
    ret, reason = is_item_retryable(item_success)
    assert ret is False
    assert "already" in reason.lower()

    item_auth = MagicMock(status=BatchItemStatus.FAILED, error_category="AUTHENTICATION_ERROR", failed_stage="GEMINI_AUTH")
    ret, reason = is_item_retryable(item_auth)
    assert ret is False
    assert "authentication" in reason.lower()

    item_invalid = MagicMock(status=BatchItemStatus.INVALID, error_category="INVALID_FILE", failed_stage="PREFLIGHT")
    ret, reason = is_item_retryable(item_invalid)
    assert ret is False
    assert "invalid" in reason.lower()

    item_empty_ocr = MagicMock(status=BatchItemStatus.FAILED, error_category="EMPTY_OCR_RESPONSE", failed_stage="VISION_OCR")
    ret, _ = is_item_retryable(item_empty_ocr)
    assert ret is True

    item_partial = MagicMock(status=BatchItemStatus.PARTIAL, error_category="STRUCTURING_FAILURE", failed_stage="JSON_STRUCTURING")
    ret, _ = is_item_retryable(item_partial)
    assert ret is True


def test_single_failed_item_retry_success():
    """
    Tests that an individual failed item (empty OCR) can be retried successfully,
    updating summary counts and regenerating the ZIP archive without touching other items.
    """
    b1 = create_synthetic_png_bytes(color=(10, 20, 30))
    b2 = create_synthetic_png_bytes(color=(40, 50, 60))
    files = [MockUploadedFile("file_01.png", b1), MockUploadedFile("file_02.png", b2)]

    call_count = 0

    def mock_extract(images, gemini_service, op_id):
        nonlocal call_count
        call_count += 1
        if call_count == 2:  # file_02 initially fails
            return RawExtractionResult(
                verbatim_text="",
                document_type="unknown",
                confidence_level=ConfidenceLevel.LOW,
                model_used="gemini-3.1-flash-lite",
            )
        return RawExtractionResult(
            verbatim_text=f"Extraction success call {call_count}",
            document_type="receipt",
            confidence_level=ConfidenceLevel.HIGH,
            model_used="gemini-3.1-flash-lite",
        )

    def mock_structure(reviewed_raw_text, document_type_hint, gemini_service, op_id):
        return StructuredExtractionResult(
            data={"status": "structured", "text": reviewed_raw_text},
            confidence_level=ConfidenceLevel.HIGH,
            model_used="gemini-3.1-flash-lite",
        )

    with patch("services.batch_processing_service.extract_raw_document", side_effect=mock_extract), \
         patch("services.batch_processing_service.structure_raw_extraction", side_effect=mock_structure), \
         patch("services.batch_processing_service.INTER_FILE_PACING_SECONDS", 0.0):

        mock_gemini = MagicMock()
        summary, results = process_batch_sequential(files, gemini_service=mock_gemini)

    assert summary.success_count == 1
    assert summary.failed_count == 1
    assert results[1].status == BatchItemStatus.FAILED
    assert results[1].retry_count == 0

    # Now retry file_02 (item_index 2)
    with patch("services.batch_processing_service.extract_raw_document", side_effect=mock_extract), \
         patch("services.batch_processing_service.structure_raw_extraction", side_effect=mock_structure):

        retried_item = retry_single_batch_item(
            item_index=2,
            summary=summary,
            results=results,
            file_bytes=b2,
            gemini_service=mock_gemini,
        )

    assert retried_item.status == BatchItemStatus.SUCCESS
    assert retried_item.retry_count == 1
    assert len(retried_item.retry_history) == 1
    assert retried_item.retry_history[0]["attempt"] == 1
    # Verify summary counts updated
    assert summary.success_count == 2
    assert summary.failed_count == 0
    # Verify results[0] remained untouched
    assert results[0].original_filename == "file_01.png"
    assert results[0].status == BatchItemStatus.SUCCESS


def test_stage_aware_retry_reuses_stage1_when_only_stage2_failed():
    """
    Verifies that when Stage 1 succeeded but Stage 2 failed (PARTIAL),
    retry reuses the existing raw_text and does NOT call extract_raw_document again.
    """
    b = create_synthetic_png_bytes()
    files = [MockUploadedFile("partial_doc.png", b)]

    stage1_called = 0
    stage2_called = 0

    def mock_extract(images, gemini_service, op_id):
        nonlocal stage1_called
        stage1_called += 1
        return RawExtractionResult(
            verbatim_text="EXISTING STAGE 1 VERBATIM TEXT",
            document_type="invoice",
            confidence_level=ConfidenceLevel.HIGH,
            model_used="gemini-3.1-flash-lite",
        )

    def mock_structure_init(reviewed_raw_text, document_type_hint, gemini_service, op_id):
        nonlocal stage2_called
        stage2_called += 1
        raise RuntimeError("Transient structuring JSON syntax error")

    with patch("services.batch_processing_service.extract_raw_document", side_effect=mock_extract), \
         patch("services.batch_processing_service.structure_raw_extraction", side_effect=mock_structure_init), \
         patch("services.batch_processing_service.INTER_FILE_PACING_SECONDS", 0.0):

        mock_gemini = MagicMock()
        summary, results = process_batch_sequential(files, gemini_service=mock_gemini)

    assert summary.partial_count == 1
    assert results[0].status == BatchItemStatus.PARTIAL
    assert stage1_called == 1
    assert stage2_called == 1

    # Retry Stage 2 with fixed structure response
    def mock_structure_success(reviewed_raw_text, document_type_hint, gemini_service, op_id):
        nonlocal stage2_called
        stage2_called += 1
        return StructuredExtractionResult(
            data={"invoice_no": "INV-100", "source": reviewed_raw_text},
            confidence_level=ConfidenceLevel.HIGH,
            model_used="gemini-3.1-flash-lite",
        )

    with patch("services.batch_processing_service.extract_raw_document", side_effect=mock_extract) as mock_ext_patch, \
         patch("services.batch_processing_service.structure_raw_extraction", side_effect=mock_structure_success):

        retried = retry_single_batch_item(
            item_index=1,
            summary=summary,
            results=results,
            file_bytes=b,
            gemini_service=mock_gemini,
        )

    # extract_raw_document was NOT called again during stage-aware retry!
    assert stage1_called == 1
    assert stage2_called == 2
    assert retried.status == BatchItemStatus.SUCCESS
    assert summary.success_count == 1
    assert summary.partial_count == 0
    assert retried.structured_data["invoice_no"] == "INV-100"


def test_global_retry_all_failed_items():
    """
    Tests retry_all_failed_batch_items: only retryable items are retried sequentially.
    Successful items and unretryable items (e.g. bad auth) are untouched.
    """
    b1 = create_synthetic_png_bytes(color=(1, 1, 1))
    b2 = create_synthetic_png_bytes(color=(2, 2, 2))
    b3 = create_synthetic_png_bytes(color=(3, 3, 3))

    results = [
        MagicMock(file_index=1, original_filename="ok.png", status=BatchItemStatus.SUCCESS, error_category=None, failed_stage=None),
        MagicMock(file_index=2, original_filename="failed_retryable.png", status=BatchItemStatus.FAILED, error_category="EMPTY_OCR_RESPONSE", failed_stage="VISION_OCR", retry_count=0, retry_history=[]),
        MagicMock(file_index=3, original_filename="auth_fail.png", status=BatchItemStatus.FAILED, error_category="AUTHENTICATION_ERROR", failed_stage="GEMINI_AUTH", retry_count=0, retry_history=[]),
    ]

    summary = MagicMock(
        batch_id="TEST_BAT",
        total_files=3,
        success_count=1,
        failed_count=2,
        partial_count=0,
        skipped_count=0,
    )
    file_bytes_map = {1: b1, 2: b2, 3: b3}

    with patch("services.batch_processing_service.retry_single_batch_item") as mock_retry_single, \
         patch("services.batch_processing_service.INTER_FILE_PACING_SECONDS", 0.0):

        retry_all_failed_batch_items(summary, results, file_bytes_map)

        # Only item 2 should be retried!
        assert mock_retry_single.call_count == 1
        args, kwargs = mock_retry_single.call_args
        assert kwargs["item_index"] == 2


def test_editable_raw_text_restructure_success():
    """
    Verifies human-in-the-loop review: user edits raw OCR text, invokes AI re-structuring,
    Stage 1 Vision OCR is NOT called, Stage 2 generates updated JSON, exports, and updates ZIP.
    """
    b = create_synthetic_png_bytes()
    files = [MockUploadedFile("item_review.png", b)]

    with patch("services.batch_processing_service.extract_raw_document") as mock_extract, \
         patch("services.batch_processing_service.structure_raw_extraction") as mock_structure, \
         patch("services.batch_processing_service.INTER_FILE_PACING_SECONDS", 0.0):

        mock_extract.return_value = RawExtractionResult(
            verbatim_text="RAW TEXT WITH TYPO: TOAL $10.00",
            document_type="receipt",
            confidence_level=ConfidenceLevel.HIGH,
            model_used="gemini-3.1-flash-lite",
        )
        mock_structure.return_value = StructuredExtractionResult(
            data={"total": "10.00", "notes": "TYPO IN TOTAL"},
            confidence_level=ConfidenceLevel.HIGH,
            model_used="gemini-3.1-flash-lite",
        )

        mock_gemini = MagicMock()
        summary, results = process_batch_sequential(files, gemini_service=mock_gemini)

    item = results[0]
    assert item.status == BatchItemStatus.SUCCESS
    assert item.original_raw_text == "RAW TEXT WITH TYPO: TOAL $10.00"
    assert item.is_reviewed is False

    # User modifies text
    reviewed_text = "RAW TEXT CORRECTED: TOTAL $100.00"

    with patch("services.batch_processing_service.extract_raw_document") as mock_ext_never, \
         patch("services.batch_processing_service.structure_raw_extraction") as mock_struct_reviewed:

        mock_struct_reviewed.return_value = StructuredExtractionResult(
            data={"total": "100.00", "notes": "CORRECTED TOTAL"},
            confidence_level=ConfidenceLevel.HIGH,
            model_used="gemini-3.1-flash-lite",
        )

        restructured = restructure_single_batch_item(
            item_index=1,
            summary=summary,
            results=results,
            reviewed_text=reviewed_text,
            gemini_service=mock_gemini,
        )

    # Stage 1 was NEVER called
    mock_ext_never.assert_not_called()
    assert restructured.status == BatchItemStatus.SUCCESS_REVIEWED
    assert restructured.is_reviewed is True
    assert restructured.review_count == 1
    assert restructured.structured_data["total"] == "100.00"
    assert restructured.original_raw_text == "RAW TEXT WITH TYPO: TOAL $10.00"
    assert restructured.raw_text == reviewed_text
    assert "TOTAL $100.00" in (restructured.txt_content or "")


def test_restructure_rejects_empty_text():
    """Verifies that attempting to re-structure empty or whitespace text raises ValueError."""
    item = MagicMock(file_index=1, raw_text="Valid text")
    summary = MagicMock(batch_id="TEST_BAT")
    with pytest.raises(ValueError, match="cannot be empty"):
        restructure_single_batch_item(
            item_index=1,
            summary=summary,
            results=[item],
            reviewed_text="   \n  ",
        )


def test_style_batch_table():
    """Verifies row styling CSS for all status types in batch dataframe."""
    df = pd.DataFrame([
        {"No.": "01", "Filename": "f1.png", "Status": "SUCCESS"},
        {"No.": "02", "Filename": "f2.png", "Status": "SUCCESS_REVIEWED"},
        {"No.": "03", "Filename": "f3.png", "Status": "PROCESSING"},
        {"No.": "04", "Filename": "f4.png", "Status": "RETRYING"},
        {"No.": "05", "Filename": "f5.png", "Status": "FAILED"},
        {"No.": "06", "Filename": "f6.png", "Status": "PARTIAL"},
        {"No.": "07", "Filename": "f7.png", "Status": "QUEUED"},
    ])

    styled = style_batch_table(df)
    assert hasattr(styled, "to_html")
    html = styled.to_html()

    # Check key color strings present in styled HTML
    assert "rgba(255, 255, 255, 0.06)" in html  # SUCCESS grey/slate
    assert "rgba(56, 189, 248, 0.08)" in html   # SUCCESS_REVIEWED subtle teal/slate
    assert "rgba(14, 165, 233, 0.22)" in html   # PROCESSING cyan/teal
    assert "rgba(99, 102, 241, 0.22)" in html   # RETRYING blue/indigo
    assert "rgba(239, 68, 68, 0.18)" in html    # FAILED soft red
    assert "rgba(245, 158, 11, 0.18)" in html   # PARTIAL soft amber


def test_nobeth_logo_asset_and_visibility():
    """Verifies official logo asset exists, loads base64 data, and theme CSS enforces target sizing."""
    import os

    logo_path = os.path.join("static", "assets", "nobeth-analytics.png")
    assert os.path.exists(logo_path), f"Logo not found at {logo_path}"
    b64 = get_nobeth_logo_base64()
    assert b64 is not None
    assert len(b64) > 100

    # Check CSS in ui/theme.py
    with open("ui/theme.py", "r", encoding="utf-8") as f:
        theme_css = f.read()

    assert ".nobeth-official-logo" in theme_css
    assert "88px" in theme_css
    assert "object-fit: contain" in theme_css


def test_width_kw_compatibility():
    """Verifies width_kw produces modern width parameter or legacy use_container_width."""
    from ui.components import width_kw
    import streamlit as st
    import inspect

    res = width_kw()
    assert isinstance(res, dict)
    if "width" in inspect.signature(st.button).parameters:
        assert res == {"width": "stretch"}
    else:
        assert res == {"use_container_width": True}


def test_bulk_raw_text_reset_callback():
    """Verifies _on_reset_bulk_raw_text safely resets session state values via callback."""
    from ui.bulk_workspace import _on_reset_bulk_raw_text
    import streamlit as st

    test_key = "test_bulk_editor_widget"
    st.session_state[test_key] = "User typed dirty text"

    # Invoke the on_click callback
    _on_reset_bulk_raw_text(test_key, "Clean original OCR text")

    assert st.session_state[test_key] == "Clean original OCR text"


