"""
Comprehensive automated tests for telemetry, monotonic timing, structured logging,
and progress monitoring in Nobeth Universal OCR.
"""

import io
import logging
import time
from unittest.mock import MagicMock
from PIL import Image
import pytest

from utils.telemetry import (
    OperationTimer,
    format_duration,
    generate_operation_id,
    sanitize_log_message,
    setup_app_logger,
    NobethLogFormatter,
    log_stage_start,
    log_stage_success,
    log_stage_failure,
    log_operation_banner,
    log_operation_summary,
)
from services.extraction_service import extract_raw_document
from services.structuring_service import structure_raw_extraction
from services.preprocessing_service import assess_document_readiness, preprocess_document_for_vision
from services.export_service import create_export_bundle


# ==============================================================================
# 1. TIMING TESTS
# ==============================================================================
def test_monotonic_timer_duration_measurement():
    timer = OperationTimer("TEST-01")
    assert timer.op_id == "TEST-01"
    
    # Check elapsed is non-negative and monotonic
    time.sleep(0.01)
    e1 = timer.elapsed()
    assert e1 >= 0.009
    
    time.sleep(0.01)
    e2 = timer.elapsed()
    assert e2 > e1
    
    # Stage timing
    timer.start_stage("STAGE_A")
    time.sleep(0.015)
    dur_a = timer.end_stage("STAGE_A")
    assert dur_a >= 0.014
    assert timer.get_stage_duration("STAGE_A") == dur_a

    # Total stopped duration
    total = timer.stop()
    assert total >= dur_a
    # Subsequent stop calls should return consistent value
    assert timer.stop() == total


def test_format_duration_ms_and_seconds():
    # Negative / None / Zero
    assert format_duration(None) == "0 ms"
    assert format_duration(-5.0) == "0 ms"
    assert format_duration(0.0) == "0 ms"

    # Sub-second formatting in milliseconds
    assert format_duration(0.014) == "14 ms"
    assert format_duration(0.240) == "240 ms"
    assert format_duration(0.999) == "999 ms"

    # Multi-second formatting
    assert format_duration(1.000) == "1.00 s"
    assert format_duration(1.824) == "1.82 s"
    assert format_duration(12.456) == "12.46 s"
    assert format_duration(59.99) == "59.99 s"

    # Minute formatting
    assert format_duration(65.5) == "1m 5.5s"
    assert format_duration(125.0) == "2m 5.0s"


def test_operation_id_generation():
    op1 = generate_operation_id("OCR")
    op2 = generate_operation_id("STR")
    op3 = generate_operation_id("OCR")

    assert op1.startswith("OCR-")
    assert op2.startswith("STR-")
    assert op1 != op2
    assert op1 != op3
    assert len(op1) >= 8


# ==============================================================================
# 2. LOGGING TESTS
# ==============================================================================
def test_idempotent_logger_setup():
    logger1 = setup_app_logger("test_idempotent_logger")
    initial_handler_count = len(logger1.handlers)
    assert initial_handler_count >= 1

    # Call setup multiple times
    logger2 = setup_app_logger("test_idempotent_logger")
    logger3 = setup_app_logger("test_idempotent_logger")

    assert len(logger2.handlers) == initial_handler_count
    assert len(logger3.handlers) == initial_handler_count


def test_structured_log_formatter_and_output_fields():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    formatter = NobethLogFormatter()
    handler.setFormatter(formatter)

    test_logger = logging.getLogger("test_structured_formatter")
    test_logger.setLevel(logging.INFO)
    test_logger.propagate = False
    test_logger.handlers = [handler]

    test_logger.info("Test message", extra={"op_id": "OCR-9999", "stage": "VISION_OCR", "event": "SUCCESS"})

    output = stream.getvalue()
    assert "INFO" in output
    assert "OCR-9999" in output
    assert "VISION_OCR" in output
    assert "SUCCESS" in output
    assert "Test message" in output


def test_log_sanitizer_prevents_secret_leakage():
    # API key pattern
    test_key = "AIzaSyDummyKeyForTestingSanitization123"
    msg_with_key = f"api_key: {test_key}"
    sanitized = sanitize_log_message(msg_with_key)
    assert test_key not in sanitized
    assert "REDACTED" in sanitized

    # Bearer token
    msg_bearer = "Authorization: Bearer secret_token_xyz123"
    sanitized_bearer = sanitize_log_message(msg_bearer)
    assert "secret_token_xyz123" not in sanitized_bearer
    assert "REDACTED" in sanitized_bearer


# ==============================================================================
# 3. PROGRESS CALLBACK AND SERVICE INSTRUMENTATION TESTS
# ==============================================================================
def test_extract_raw_document_progress_callbacks():
    mock_service = MagicMock()
    mock_service.generate_vision_content.return_value = (
        "=== METADATA ===\n"
        "DOCUMENT_TYPE: invoice\n"
        "CONFIDENCE_LEVEL: HIGH\n"
        "=== RAW_TEXT ===\n"
        "Sample Invoice Item $10\n"
    )

    recorded_stages = []

    def on_progress(stage, ratio, meta):
        recorded_stages.append((stage, ratio, meta))

    img1 = Image.new("RGB", (50, 50), color="white")
    img2 = Image.new("RGB", (50, 50), color="gray")

    res = extract_raw_document(
        [img1, img2],
        gemini_service=mock_service,
        progress_callback=on_progress,
        op_id="TEST-OCR",
    )

    stage_names = [s[0] for s in recorded_stages]
    assert "PREPARING" in stage_names
    assert "PAGE_START" in stage_names
    assert "CALLING_VISION" in stage_names
    assert "PAGE_COMPLETE" in stage_names
    assert "FINALIZING" in stage_names

    # Check multi-page page count feedback
    page_completes = [s for s in recorded_stages if s[0] == "PAGE_COMPLETE"]
    assert len(page_completes) == 2
    assert page_completes[0][2]["current_page"] == 1
    assert page_completes[1][2]["current_page"] == 2
    assert page_completes[0][1] == 0.5  # 1/2
    assert page_completes[1][1] == 1.0  # 2/2


def test_structure_raw_extraction_progress_callbacks():
    mock_service = MagicMock()
    mock_service.generate_text_content.return_value = (
        '{"document_type": "receipt", "confidence_level": "HIGH", "total": 42.50}'
    )

    recorded_stages = []

    def on_progress(stage, ratio, meta):
        recorded_stages.append((stage, ratio, meta))

    res = structure_raw_extraction(
        reviewed_raw_text="Receipt Total: 42.50",
        document_type_hint="receipt",
        gemini_service=mock_service,
        progress_callback=on_progress,
        op_id="TEST-STR",
    )

    stage_names = [s[0] for s in recorded_stages]
    assert "PREPARING_TEXT" in stage_names
    assert "SENDING_PROMPT" in stage_names
    assert "PARSING_JSON" in stage_names
    assert "EXTRACTING_TRACEABILITY" in stage_names
    assert "COMPLETE" in stage_names
    assert res.is_valid is True


def test_export_bundle_timing_and_logging():
    test_data = {"invoice_id": "INV-101", "total": 99.00, "items": [{"desc": "Item 1", "price": 99.00}]}
    raw_text = "Invoice INV-101\nTotal: 99.00"

    bundle = create_export_bundle(
        structured_data=test_data,
        raw_text=raw_text,
        base_filename="sample_test.pdf",
        document_type="invoice",
        confidence="HIGH",
        op_id="TEST-EXP",
    )

    assert bundle.base_filename == "sample_test"
    assert "INV-101" in bundle.json_content
    assert "INV-101" in bundle.csv_content
    assert "sample_test.pdf" in bundle.txt_content


def test_backward_compatibility_without_progress_callbacks():
    mock_service = MagicMock()
    mock_service.generate_vision_content.return_value = (
        "=== METADATA ===\n"
        "DOCUMENT_TYPE: memo\n"
        "CONFIDENCE_LEVEL: HIGH\n"
        "=== RAW_TEXT ===\n"
        "Meeting memo notes\n"
    )
    img = Image.new("RGB", (60, 60), color="white")

    # Calling extract_raw_document without progress_callback
    res_extract = extract_raw_document([img], gemini_service=mock_service)
    assert res_extract.document_type == "memo"
    assert "Meeting memo notes" in res_extract.verbatim_text

    # Calling structure_raw_extraction without progress_callback
    mock_service.generate_text_content.return_value = '{"document_type": "memo", "notes": "Meeting memo notes"}'
    res_struct = structure_raw_extraction(
        reviewed_raw_text=res_extract.verbatim_text,
        gemini_service=mock_service,
    )
    assert res_struct.document_type == "memo"
    assert res_struct.is_valid is True
