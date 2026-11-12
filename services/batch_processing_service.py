"""
Batch Processing Engine: Orchestrates sequential, memory-safe, multi-image document intelligence.
Processes images one-by-one with isolated error handling, rate-limit pacing, and live callbacks.
"""

import gc
import os
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image

from models.batch_schemas import (
    BatchItemResult,
    BatchItemStage,
    BatchItemStatus,
    BatchJobSummary,
    BatchPreflightItem,
    BatchPreflightSummary,
)
from services.batch_archive_service import (
    build_batch_zip_archive,
    sanitize_filename_stem,
)
from services.export_service import create_export_bundle
from services.extraction_service import extract_raw_document
from services.gemini_service import GeminiService
from services.preprocessing_service import (
    assess_document_readiness,
    preprocess_document_for_vision,
)
from services.structuring_service import structure_raw_extraction
from utils.file_utils import (
    IMAGE_EXTENSIONS,
    detect_file_format,
    format_file_size,
    validate_file_size,
)
from utils.telemetry import (
    format_duration,
    generate_operation_id,
    log_operation_banner,
    log_stage_failure,
    log_stage_start,
    log_stage_success,
)
from utils.validation import validate_upload_bytes

# Batch processing bounds
MAX_BATCH_FILES_DEFAULT = 100
MAX_SINGLE_FILE_BYTES_DEFAULT = 25 * 1024 * 1024  # 25 MB
MAX_TOTAL_BATCH_BYTES_DEFAULT = 250 * 1024 * 1024  # 250 MB
INTER_FILE_PACING_SECONDS = 0.5  # Polite delay between Gemini calls to avoid 429 quota bursts


class BatchUploadItem:
    """Represents an uploaded file item before or during batch processing."""

    def __init__(self, filename: str, file_bytes: bytes, relative_path: str = ""):
        self.filename = filename
        self.file_bytes = file_bytes
        self.relative_path = relative_path
        self.size = len(file_bytes)


def validate_batch_preflight(
    uploaded_files: List[Any],
    max_files: int = MAX_BATCH_FILES_DEFAULT,
    max_single_size: int = MAX_SINGLE_FILE_BYTES_DEFAULT,
    max_total_size: int = MAX_TOTAL_BATCH_BYTES_DEFAULT,
) -> BatchPreflightSummary:
    """
    Performs fast, non-destructive pre-flight validation on the selected batch collection.
    Categorizes each item as VALID, INVALID, or UNSUPPORTED.
    Enforces maximum file count and aggregate upload size limits.
    """
    total_selected = len(uploaded_files)
    if total_selected == 0:
        return BatchPreflightSummary(
            total_selected=0,
            valid_count=0,
            unsupported_count=0,
            invalid_count=0,
            total_upload_size=0,
            total_upload_size_str="0 B",
            is_processable=False,
            error_message="No files selected.",
        )

    if total_selected > max_files:
        return BatchPreflightSummary(
            total_selected=total_selected,
            valid_count=0,
            unsupported_count=0,
            invalid_count=0,
            total_upload_size=0,
            total_upload_size_str="0 B",
            is_processable=False,
            error_message=f"Batch size of {total_selected} files exceeds maximum limit of {max_files} files.",
        )

    items: List[BatchPreflightItem] = []
    valid_count = 0
    unsupported_count = 0
    invalid_count = 0
    total_bytes = 0

    for idx, f in enumerate(uploaded_files):
        name = getattr(f, "name", f"file_{idx+1}")
        # Support relative path if provided by folder upload
        rel_path = getattr(f, "path", "") or getattr(f, "name", "")

        # Get bytes safely
        if hasattr(f, "getvalue"):
            b = f.getvalue()
        elif hasattr(f, "read"):
            b = f.read()
            if hasattr(f, "seek"):
                f.seek(0)
        elif isinstance(f, bytes):
            b = f
        else:
            b = b""

        size = len(b)
        total_bytes += size

        if size == 0:
            invalid_count += 1
            items.append(BatchPreflightItem(
                filename=name,
                file_size=0,
                status=BatchItemStatus.INVALID,
                error_message="File is empty (0 bytes).",
                relative_path=rel_path,
            ))
            continue

        if size > max_single_size:
            invalid_count += 1
            items.append(BatchPreflightItem(
                filename=name,
                file_size=size,
                status=BatchItemStatus.INVALID,
                error_message=f"File exceeds maximum single-file limit of {format_file_size(max_single_size)}.",
                relative_path=rel_path,
            ))
            continue

        ext, mime, is_supported = detect_file_format(name, b)

        # In bulk mode, PDFs are marked as UNSUPPORTED with clear guidance
        if ext == ".pdf":
            unsupported_count += 1
            items.append(BatchPreflightItem(
                filename=name,
                file_size=size,
                status=BatchItemStatus.UNSUPPORTED,
                error_message="PDF files are supported in Single Document mode. Bulk mode currently processes image formats: JPG, PNG, WEBP, HEIC, TIFF.",
                relative_path=rel_path,
                extension=ext,
            ))
            continue

        if not is_supported or ext not in IMAGE_EXTENSIONS:
            unsupported_count += 1
            items.append(BatchPreflightItem(
                filename=name,
                file_size=size,
                status=BatchItemStatus.UNSUPPORTED,
                error_message=f"Unsupported format '{ext}'. Supported formats: JPG, PNG, WEBP, HEIC, TIFF.",
                relative_path=rel_path,
                extension=ext,
            ))
            continue

        valid_count += 1
        items.append(BatchPreflightItem(
            filename=name,
            file_size=size,
            status=BatchItemStatus.VALID,
            relative_path=rel_path,
            extension=ext,
        ))

    if total_bytes > max_total_size:
        return BatchPreflightSummary(
            total_selected=total_selected,
            valid_count=valid_count,
            unsupported_count=unsupported_count,
            invalid_count=invalid_count,
            total_upload_size=total_bytes,
            total_upload_size_str=format_file_size(total_bytes),
            is_processable=False,
            items=items,
            error_message=f"Total upload size ({format_file_size(total_bytes)}) exceeds limit of {format_file_size(max_total_size)}.",
        )

    is_processable = (valid_count > 0)

    return BatchPreflightSummary(
        total_selected=total_selected,
        valid_count=valid_count,
        unsupported_count=unsupported_count,
        invalid_count=invalid_count,
        total_upload_size=total_bytes,
        total_upload_size_str=format_file_size(total_bytes),
        is_processable=is_processable,
        items=items,
        error_message=None if is_processable else "No valid images found in the selected files.",
    )


def generate_unique_output_basenames(items: List[BatchPreflightItem]) -> Dict[int, str]:
    """
    Generates deterministic, collision-safe output stems for all batch items.
    Handles duplicate filenames like receipt.jpg, receipt.png -> receipt, receipt_2.
    """
    used_stems: Dict[str, int] = {}
    basenames: Dict[int, str] = {}

    for idx, item in enumerate(items, start=1):
        stem = sanitize_filename_stem(item.filename)
        if stem in used_stems:
            used_stems[stem] += 1
            unique_stem = f"{stem}_{used_stems[stem]}"
        else:
            used_stems[stem] = 1
            unique_stem = stem
        basenames[idx] = unique_stem

    return basenames


def process_single_batch_item(
    item_index: int,
    total_items: int,
    filename: str,
    file_bytes: bytes,
    relative_path: str,
    output_basename: str,
    gemini_service: GeminiService,
    on_stage_change: Optional[Callable[[int, int, str, BatchItemStage], None]] = None,
    op_id: Optional[str] = None,
) -> BatchItemResult:
    """
    Processes an individual image through the complete 2-stage OCR pipeline.
    Ensures memory safety: decodes only this image, processes it, and cleans up references immediately.
    """
    t_start = time.perf_counter()
    file_op_id = op_id or generate_operation_id("BAT")
    file_size = len(file_bytes)

    result = BatchItemResult(
        file_index=item_index,
        original_filename=filename,
        relative_path=relative_path,
        file_size=file_size,
        output_basename=output_basename,
        status=BatchItemStatus.PROCESSING,
        current_stage=BatchItemStage.VALIDATION,
    )

    def _notify(stage: BatchItemStage):
        result.current_stage = stage
        if on_stage_change:
            on_stage_change(item_index, total_items, filename, stage)

    # 1. Validation
    _notify(BatchItemStage.VALIDATION)
    t0_val = time.perf_counter()
    is_valid, err_msg, ext = validate_upload_bytes(filename, file_bytes)
    result.validation_duration = time.perf_counter() - t0_val

    if not is_valid:
        result.status = BatchItemStatus.INVALID
        result.failed_stage = "VALIDATION"
        result.error_category = "VALIDATION_ERROR"
        result.error_message = err_msg or "File validation failed."
        result.total_duration = time.perf_counter() - t_start
        _notify(BatchItemStage.FAILED)
        return result

    # 2. Image Decoding & Quality Assessment
    original_images: List[Image.Image] = []
    preprocessed_images: List[Image.Image] = []

    try:
        _notify(BatchItemStage.PREPROCESSING)
        t0_prep = time.perf_counter()

        readiness_report, original_images = assess_document_readiness(
            file_bytes=file_bytes,
            extension=ext,
            op_id=file_op_id,
        )
        result.readiness_score = readiness_report.readiness_score

        if not original_images:
            result.status = BatchItemStatus.FAILED
            result.failed_stage = "IMAGE_DECODING"
            result.error_category = "CORRUPT_IMAGE"
            result.error_message = "Could not decode any image pages from file."
            result.total_duration = time.perf_counter() - t_start
            _notify(BatchItemStage.FAILED)
            return result

        # Preprocessing for Vision
        preprocessed_images, _ = preprocess_document_for_vision(
            original_images=original_images,
            auto_deskew=True,
            enhance_contrast=True,
            op_id=file_op_id,
        )
        result.preprocessing_duration = time.perf_counter() - t0_prep

        # 3. Stage 1: Gemini Vision Raw Extraction
        _notify(BatchItemStage.VISION_OCR)
        t0_ocr = time.perf_counter()
        raw_result = extract_raw_document(
            images=preprocessed_images,
            gemini_service=gemini_service,
            op_id=file_op_id,
        )
        result.ocr_duration = time.perf_counter() - t0_ocr
        result.raw_text = raw_result.verbatim_text
        result.original_raw_text = raw_result.verbatim_text
        result.reviewed_raw_text = raw_result.verbatim_text
        result.document_type = raw_result.document_type
        result.confidence = raw_result.confidence_level.value
        result.model_used = raw_result.model_used

        if not raw_result.verbatim_text or not raw_result.verbatim_text.strip():
            result.status = BatchItemStatus.FAILED
            result.failed_stage = "VISION_OCR"
            result.error_category = "EMPTY_OCR_RESPONSE"
            result.error_message = "Gemini returned an empty extraction result."
            result.total_duration = time.perf_counter() - t_start
            _notify(BatchItemStage.FAILED)
            return result

        # 4. Stage 2: Dynamic JSON Structuring
        _notify(BatchItemStage.JSON_STRUCTURING)
        t0_struct = time.perf_counter()
        try:
            struct_result = structure_raw_extraction(
                reviewed_raw_text=raw_result.verbatim_text,
                document_type_hint=raw_result.document_type,
                gemini_service=gemini_service,
                op_id=file_op_id,
            )
            result.structuring_duration = time.perf_counter() - t0_struct
            result.structured_data = struct_result.data
            result.model_used = struct_result.model_used

            # 5. Export Generation (JSON, CSV, TXT)
            _notify(BatchItemStage.EXPORT)
            t0_exp = time.perf_counter()
            bundle = create_export_bundle(
                structured_data=struct_result.data,
                raw_text=raw_result.verbatim_text,
                base_filename=output_basename,
                document_type=result.document_type,
                confidence=result.confidence,
                op_id=file_op_id,
            )
            result.export_duration = time.perf_counter() - t0_exp

            result.json_filename = f"{output_basename}.json"
            result.csv_filename = f"{output_basename}.csv"
            result.txt_filename = f"{output_basename}.txt"
            result.json_content = bundle.json_content
            result.csv_content = bundle.csv_content
            result.txt_content = bundle.txt_content

            result.status = BatchItemStatus.SUCCESS
            _notify(BatchItemStage.COMPLETED)

        except Exception as struct_err:
            # Stage 1 succeeded, but Stage 2 failed -> Mark as PARTIAL (preserve Stage 1 text)
            result.structuring_duration = time.perf_counter() - t0_struct
            result.status = BatchItemStatus.PARTIAL
            result.failed_stage = "JSON_STRUCTURING"
            result.error_category = "STRUCTURING_FAILURE"
            result.error_message = str(struct_err)

            # Generate verbatim TXT export so user still gets Stage 1 result
            bundle = create_export_bundle(
                structured_data={},
                raw_text=raw_result.verbatim_text,
                base_filename=output_basename,
                document_type=result.document_type,
                confidence=result.confidence,
                op_id=file_op_id,
            )
            result.txt_filename = f"{output_basename}.txt"
            result.txt_content = bundle.txt_content
            _notify(BatchItemStage.FAILED)

    except Exception as exc:
        err_str = str(exc)
        if not err_str or "[object Object]" in err_str:
            err_str = f"Vision extraction failed ({type(exc).__name__}). The document image may be corrupt, blank, or restricted by API filters."
        result.status = BatchItemStatus.FAILED
        result.error_message = err_str

        # Categorize failure
        if "429" in err_str or "quota" in err_str.lower() or "resource_exhausted" in err_str.lower():
            result.error_category = "RATE_LIMIT_EXCEEDED"
            result.failed_stage = "GEMINI_API"
        elif "504" in err_str or "timed out" in err_str.lower():
            result.error_category = "TIMEOUT"
            result.failed_stage = "GEMINI_NETWORK"
        elif "503" in err_str or "unavailable" in err_str.lower():
            result.error_category = "SERVICE_UNAVAILABLE"
            result.failed_stage = "GEMINI_NETWORK"
        elif "api_key" in err_str.lower() or "unauthenticated" in err_str.lower():
            result.error_category = "AUTHENTICATION_ERROR"
            result.failed_stage = "GEMINI_AUTH"
        else:
            result.error_category = "PROCESSING_ERROR"
            result.failed_stage = result.current_stage.value

        _notify(BatchItemStage.FAILED)

    finally:
        # STRICT MEMORY CLEANUP: Release PIL Image memory immediately
        for img in original_images:
            try:
                img.close()
            except Exception:
                pass
        for img in preprocessed_images:
            try:
                img.close()
            except Exception:
                pass
        original_images.clear()
        preprocessed_images.clear()
        del original_images
        del preprocessed_images

    result.total_duration = time.perf_counter() - t_start
    return result


def process_batch_sequential(
    uploaded_files: List[Any],
    gemini_service: Optional[GeminiService] = None,
    preflight: Optional[BatchPreflightSummary] = None,
    on_item_start: Optional[Callable[[int, int, str], None]] = None,
    on_stage_change: Optional[Callable[[int, int, str, BatchItemStage], None]] = None,
    on_item_complete: Optional[Callable[[int, int, BatchItemResult], None]] = None,
    batch_id: Optional[str] = None,
    archive_output_dir: Optional[str] = None,
) -> Tuple[BatchJobSummary, List[BatchItemResult]]:
    """
    Executes the strictly sequential bulk processing queue across all valid images.
    Guarantees concurrency == 1: exactly one file processed at a time.
    Provides live telemetry logs and generates complete ZIP archive upon completion.
    """
    b_id = batch_id or generate_operation_id("BAT")
    t_batch_start = time.perf_counter()
    started_at_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Run preflight if not supplied
    pf = preflight or validate_batch_preflight(uploaded_files)
    total_files = len(pf.items)

    log_operation_banner(b_id, "BULK IMAGE PROCESSING")
    print(f"BATCH ID : {b_id}")
    print(f"TOTAL    : {total_files} FILES (Valid: {pf.valid_count}, Unsupported: {pf.unsupported_count}, Invalid: {pf.invalid_count})")
    print("STRATEGY : STRICTLY SEQUENTIAL (Concurrency: 1)\n")

    # Generate collision-safe output basenames
    basenames = generate_unique_output_basenames(pf.items)

    service = gemini_service or GeminiService()
    results: List[BatchItemResult] = []

    success_count = 0
    partial_count = 0
    failed_count = 0
    skipped_count = 0
    fatal_error_occurred = False
    fatal_error_reason = ""

    for idx, pre_item in enumerate(pf.items, start=1):
        filename = pre_item.filename
        rel_path = pre_item.relative_path
        out_base = basenames[idx]

        if on_item_start:
            on_item_start(idx, total_files, filename)

        # 1. Handle preflight failures (unsupported or invalid)
        if pre_item.status == BatchItemStatus.INVALID:
            failed_count += 1
            res = BatchItemResult(
                file_index=idx,
                original_filename=filename,
                relative_path=rel_path,
                file_size=pre_item.file_size,
                output_basename=out_base,
                status=BatchItemStatus.INVALID,
                current_stage=BatchItemStage.FAILED,
                failed_stage="PREFLIGHT",
                error_category="INVALID_FILE",
                error_message=pre_item.error_message or "Invalid file.",
                total_duration=0.0,
            )
            results.append(res)
            if on_item_complete:
                on_item_complete(idx, total_files, res)
            continue

        if pre_item.status == BatchItemStatus.UNSUPPORTED:
            skipped_count += 1
            res = BatchItemResult(
                file_index=idx,
                original_filename=filename,
                relative_path=rel_path,
                file_size=pre_item.file_size,
                output_basename=out_base,
                status=BatchItemStatus.UNSUPPORTED,
                current_stage=BatchItemStage.SKIPPED,
                failed_stage="PREFLIGHT",
                error_category="UNSUPPORTED_FORMAT",
                error_message=pre_item.error_message or "Unsupported format.",
                total_duration=0.0,
            )
            results.append(res)
            if on_item_complete:
                on_item_complete(idx, total_files, res)
            continue

        # 2. Check if previous item hit a fatal error (Auth error or permanent Quota exhaustion)
        if fatal_error_occurred:
            skipped_count += 1
            res = BatchItemResult(
                file_index=idx,
                original_filename=filename,
                relative_path=rel_path,
                file_size=pre_item.file_size,
                output_basename=out_base,
                status=BatchItemStatus.SKIPPED,
                current_stage=BatchItemStage.SKIPPED,
                failed_stage="SKIPPED",
                error_category="QUEUE_HALTED",
                error_message=f"Skipped due to earlier fatal batch error: {fatal_error_reason}",
                total_duration=0.0,
            )
            results.append(res)
            if on_item_complete:
                on_item_complete(idx, total_files, res)
            continue

        # Extract file bytes safely
        raw_obj = uploaded_files[idx - 1]
        if hasattr(raw_obj, "getvalue"):
            file_bytes = raw_obj.getvalue()
        elif hasattr(raw_obj, "read"):
            file_bytes = raw_obj.read()
            if hasattr(raw_obj, "seek"):
                raw_obj.seek(0)
        elif isinstance(raw_obj, bytes):
            file_bytes = raw_obj
        else:
            file_bytes = b""

        # Log item start to terminal
        print(f"[{idx:02d}/{total_files:02d}] {filename} ({format_file_size(len(file_bytes))})")

        # Process strictly one file
        item_res = process_single_batch_item(
            item_index=idx,
            total_items=total_files,
            filename=filename,
            file_bytes=file_bytes,
            relative_path=rel_path,
            output_basename=out_base,
            gemini_service=service,
            on_stage_change=on_stage_change,
            op_id=b_id,
        )

        results.append(item_res)

        # Track statistics
        if item_res.status == BatchItemStatus.SUCCESS:
            success_count += 1
            status_tag = "SUCCESS"
        elif item_res.status == BatchItemStatus.PARTIAL:
            partial_count += 1
            status_tag = "PARTIAL"
        else:
            failed_count += 1
            status_tag = "FAILED"

        dur_str = format_duration(item_res.total_duration or 0.0)
        print(f"        FILE RESULT         {status_tag:10s}   {dur_str} (Model: {item_res.model_used or 'N/A'})\n")

        # Check for fatal conditions (Auth error)
        if item_res.error_category in ["AUTHENTICATION_ERROR"]:
            fatal_error_occurred = True
            fatal_error_reason = item_res.error_message or "Authentication failure."
            print(f"[*] Fatal error detected ({fatal_error_reason}). Halting remaining queue safely.\n")

        if on_item_complete:
            on_item_complete(idx, total_files, item_res)

        # Gentle pacing delay between Gemini calls to avoid 429 quota bursts
        if idx < total_files and not fatal_error_occurred:
            time.sleep(INTER_FILE_PACING_SECONDS)

        # Explicit garbage collection pass every 5 items to keep memory footprint minimal
        if idx % 5 == 0:
            gc.collect()

    total_batch_duration = time.perf_counter() - t_batch_start
    finished_at_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    completed_count = len(results)
    avg_duration = (total_batch_duration / completed_count) if completed_count > 0 else 0.0

    # Build summary
    summary = BatchJobSummary(
        batch_id=b_id,
        batch_started_at=started_at_str,
        batch_finished_at=finished_at_str,
        total_files=total_files,
        valid_count=pf.valid_count,
        completed_count=completed_count,
        success_count=success_count,
        partial_count=partial_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        total_duration=total_batch_duration,
        average_duration_per_item=avg_duration,
    )

    # Build Complete ZIP Archive
    try:
        zip_path, zip_name, zip_size = build_batch_zip_archive(
            summary=summary,
            items=results,
            output_dir=archive_output_dir,
        )
        summary.zip_archive_path = zip_path
        summary.zip_filename = zip_name
        archive_status = f"READY ({format_file_size(zip_size)})"
    except Exception as zip_err:
        archive_status = f"FAILED ({zip_err})"

    # Print Batch Summary to terminal
    print("======================================================================")
    print(" BATCH SUMMARY")
    print("======================================================================")
    print(f"BATCH ID          : {b_id}")
    print(f"TOTAL FILES       : {total_files}")
    print(f"SUCCESSFUL        : {success_count}")
    print(f"PARTIAL           : {partial_count}")
    print(f"FAILED            : {failed_count}")
    print(f"SKIPPED           : {skipped_count}")
    print(f"TOTAL DURATION    : {format_duration(total_batch_duration)}")
    print(f"RESULT ARCHIVE    : {archive_status}")
    print("======================================================================\n")

    return summary, results


def is_item_retryable(item: BatchItemResult) -> Tuple[bool, str]:
    """
    Evaluates whether an individual batch item is eligible for retry.
    Returns: (is_eligible, explanation)
    """
    if item.status in [BatchItemStatus.SUCCESS, BatchItemStatus.SUCCESS_REVIEWED]:
        return False, "Image has already been processed successfully."

    if item.error_category in ["AUTHENTICATION_ERROR", "INVALID_API_KEY"] or item.failed_stage == "GEMINI_AUTH":
        return False, "Cannot retry automatically: Gemini API authentication issue. Please check your API key in .env."

    if item.status == BatchItemStatus.INVALID or item.error_category in ["INVALID_FILE", "VALIDATION_ERROR"]:
        return False, "Cannot retry: File is invalid or 0 bytes. Correct the file before processing."

    if item.status == BatchItemStatus.UNSUPPORTED:
        return False, "Cannot retry: Format is unsupported in bulk mode."

    return True, "Item is eligible for stage-aware retry."


def retry_single_batch_item(
    item_index: int,
    summary: BatchJobSummary,
    results: List[BatchItemResult],
    file_bytes: bytes,
    gemini_service: Optional[GeminiService] = None,
    op_id: Optional[str] = None,
    on_stage_change: Optional[Callable[[int, int, str, BatchItemStage], None]] = None,
    archive_output_dir: Optional[str] = None,
) -> BatchItemResult:
    """
    Re-runs an individual failed or partial batch item with stage-awareness.
    Preserves all other items untouched, updates summary counts, and regenerates the ZIP archive atomically.
    """
    if item_index < 1 or item_index > len(results):
        raise IndexError(f"Item index {item_index} out of range (1..{len(results)})")

    target = results[item_index - 1]
    is_ret, reason = is_item_retryable(target)
    if not is_ret:
        raise ValueError(f"Item {item_index} is not eligible for retry: {reason}")

    service = gemini_service or GeminiService()
    batch_op_id = op_id or summary.batch_id
    t_start = time.perf_counter()

    # Record retry attempt in history
    attempt_num = target.retry_count + 1
    target.retry_count = attempt_num
    target.retry_history.append({
        "attempt": attempt_num,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "failed_stage": target.failed_stage,
        "error_category": target.error_category,
        "error_message": target.error_message,
    })

    print(f"\n[{batch_op_id}] IMAGE {item_index:02d}/{summary.total_files:02d} | RETRY START (Attempt {attempt_num})")

    # Change status to RETRYING
    target.status = BatchItemStatus.RETRYING
    if on_stage_change:
        on_stage_change(item_index, summary.total_files, target.original_filename, BatchItemStage.QUEUED)

    # STAGE-AWARE EXECUTION:
    # Case A: Stage 1 already succeeded, but Stage 2 failed (PARTIAL)
    if target.failed_stage == "JSON_STRUCTURING" and target.raw_text and target.raw_text.strip():
        print(f"[{batch_op_id}] IMAGE {item_index:02d}/{summary.total_files:02d} | REUSING STAGE 1 OCR -> RETRYING STAGE 2 STRUCTURING")
        if on_stage_change:
            on_stage_change(item_index, summary.total_files, target.original_filename, BatchItemStage.JSON_STRUCTURING)

        t0_struct = time.perf_counter()
        try:
            struct_result = structure_raw_extraction(
                reviewed_raw_text=target.raw_text,
                document_type_hint=target.document_type,
                gemini_service=service,
                op_id=batch_op_id,
            )
            target.structuring_duration = time.perf_counter() - t0_struct
            target.structured_data = struct_result.data
            target.model_used = struct_result.model_used

            # Export generation
            if on_stage_change:
                on_stage_change(item_index, summary.total_files, target.original_filename, BatchItemStage.EXPORT)

            t0_exp = time.perf_counter()
            bundle = create_export_bundle(
                structured_data=struct_result.data,
                raw_text=target.raw_text,
                base_filename=target.output_basename,
                document_type=target.document_type,
                confidence=target.confidence,
                op_id=batch_op_id,
            )
            target.export_duration = time.perf_counter() - t0_exp
            target.json_filename = f"{target.output_basename}.json"
            target.csv_filename = f"{target.output_basename}.csv"
            target.txt_filename = f"{target.output_basename}.txt"
            target.json_content = bundle.json_content
            target.csv_content = bundle.csv_content
            target.txt_content = bundle.txt_content

            target.status = BatchItemStatus.SUCCESS
            target.current_stage = BatchItemStage.COMPLETED
            target.failed_stage = None
            target.error_category = None
            target.error_message = None
            target.total_duration = (target.ocr_duration or 0.0) + target.structuring_duration + (target.export_duration or 0.0)
            print(f"[{batch_op_id}] IMAGE {item_index:02d}/{summary.total_files:02d} | RETRY SUCCESS | Structuring: {format_duration(target.structuring_duration)}")
        except Exception as exc:
            target.structuring_duration = time.perf_counter() - t0_struct
            target.status = BatchItemStatus.PARTIAL
            target.failed_stage = "JSON_STRUCTURING"
            target.error_category = "STRUCTURING_FAILURE"
            target.error_message = str(exc)
            target.total_duration = time.perf_counter() - t_start
            print(f"[{batch_op_id}] IMAGE {item_index:02d}/{summary.total_files:02d} | RETRY FAILED | {exc}")

    else:
        # Case B: Stage 1 failed (e.g. empty OCR, decoding, or API timeout)
        # Re-run full pipeline for this item
        print(f"[{batch_op_id}] IMAGE {item_index:02d}/{summary.total_files:02d} | RUNNING FULL RETRY (PREPROCESSING -> OCR -> STRUCTURING)")
        retried_result = process_single_batch_item(
            item_index=item_index,
            total_items=summary.total_files,
            filename=target.original_filename,
            file_bytes=file_bytes,
            relative_path=target.relative_path,
            output_basename=target.output_basename,
            gemini_service=service,
            on_stage_change=on_stage_change,
            op_id=batch_op_id,
        )
        # Preserve retry count and history
        retried_result.retry_count = attempt_num
        retried_result.retry_history = target.retry_history
        retried_result.is_reviewed = target.is_reviewed
        retried_result.review_count = target.review_count
        results[item_index - 1] = retried_result
        target = retried_result
        print(f"[{batch_op_id}] IMAGE {item_index:02d}/{summary.total_files:02d} | RETRY COMPLETED | Status: {target.status.value}")

    # Recalculate summary metrics
    summary.success_count = sum(1 for r in results if r.status in [BatchItemStatus.SUCCESS, BatchItemStatus.SUCCESS_REVIEWED])
    summary.partial_count = sum(1 for r in results if r.status == BatchItemStatus.PARTIAL)
    summary.failed_count = sum(1 for r in results if r.status in [BatchItemStatus.FAILED, BatchItemStatus.INVALID])
    summary.skipped_count = sum(1 for r in results if r.status in [BatchItemStatus.SKIPPED, BatchItemStatus.UNSUPPORTED])

    # Regenerate batch ZIP archive atomically
    try:
        zip_path, zip_name, zip_size = build_batch_zip_archive(
            summary=summary,
            items=results,
            output_dir=archive_output_dir,
        )
        summary.zip_archive_path = zip_path
        summary.zip_filename = zip_name
        print(f"[{batch_op_id}] BATCH ZIP ATOMICALLY REGENERATED | {zip_name} ({format_file_size(zip_size)})\n")
    except Exception as zip_err:
        print(f"[{batch_op_id}] WARNING: Batch ZIP regeneration failed: {zip_err}\n")

    return target


def restructure_single_batch_item(
    item_index: int,
    summary: BatchJobSummary,
    results: List[BatchItemResult],
    reviewed_text: str,
    gemini_service: Optional[GeminiService] = None,
    op_id: Optional[str] = None,
    archive_output_dir: Optional[str] = None,
) -> BatchItemResult:
    """
    Re-structures dynamic JSON using human-reviewed verbatim raw text.
    STRICT REQUIREMENT: Stage 1 Vision OCR is NOT rerun. Only Stage 2 Structuring, validation,
    traceability, and export generation execute.
    Atomically regenerates the batch ZIP archive and updates manifest.
    """
    if item_index < 1 or item_index > len(results):
        raise IndexError(f"Item index {item_index} out of range (1..{len(results)})")

    if not reviewed_text or not reviewed_text.strip():
        raise ValueError("Reviewed raw text cannot be empty.")

    target = results[item_index - 1]
    service = gemini_service or GeminiService()
    batch_op_id = op_id or summary.batch_id
    t_start = time.perf_counter()

    print(f"\n[{batch_op_id}] IMAGE {item_index:02d}/{summary.total_files:02d} | REVIEWED TEXT STRUCTURING START")

    # Preserve original raw text if not yet set
    if not target.original_raw_text and target.raw_text:
        target.original_raw_text = target.raw_text

    target.reviewed_raw_text = reviewed_text.strip()
    target.raw_text = reviewed_text.strip()  # Update active raw text to reviewed version

    # Stage 2 Structuring using reviewed text ONLY (No Stage 1 OCR!)
    t0_struct = time.perf_counter()
    struct_result = structure_raw_extraction(
        reviewed_raw_text=target.raw_text,
        document_type_hint=target.document_type,
        gemini_service=service,
        op_id=batch_op_id,
    )
    struct_dur = time.perf_counter() - t0_struct

    # Update item record
    target.structured_data = struct_result.data
    target.structuring_duration = struct_dur
    target.model_used = struct_result.model_used
    target.is_reviewed = True
    target.review_count += 1
    target.status = BatchItemStatus.SUCCESS_REVIEWED
    target.current_stage = BatchItemStage.COMPLETED
    target.last_modified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    target.failed_stage = None
    target.error_category = None
    target.error_message = None

    # Regenerate Export Bundle (JSON, CSV, TXT)
    t0_exp = time.perf_counter()
    bundle = create_export_bundle(
        structured_data=struct_result.data,
        raw_text=target.raw_text,
        base_filename=target.output_basename,
        document_type=target.document_type,
        confidence=target.confidence,
        op_id=batch_op_id,
    )
    target.export_duration = time.perf_counter() - t0_exp
    target.json_filename = f"{target.output_basename}.json"
    target.csv_filename = f"{target.output_basename}.csv"
    target.txt_filename = f"{target.output_basename}.txt"
    target.json_content = bundle.json_content
    target.csv_content = bundle.csv_content
    target.txt_content = bundle.txt_content
    target.total_duration = (target.ocr_duration or 0.0) + struct_dur + (target.export_duration or 0.0)

    print(f"[{batch_op_id}] IMAGE {item_index:02d}/{summary.total_files:02d} | RE-STRUCTURING SUCCESS ({format_duration(struct_dur)})")

    # Recalculate summary metrics
    summary.success_count = sum(1 for r in results if r.status in [BatchItemStatus.SUCCESS, BatchItemStatus.SUCCESS_REVIEWED])
    summary.partial_count = sum(1 for r in results if r.status == BatchItemStatus.PARTIAL)
    summary.failed_count = sum(1 for r in results if r.status in [BatchItemStatus.FAILED, BatchItemStatus.INVALID])
    summary.skipped_count = sum(1 for r in results if r.status in [BatchItemStatus.SKIPPED, BatchItemStatus.UNSUPPORTED])

    # Regenerate batch ZIP archive atomically
    try:
        zip_path, zip_name, zip_size = build_batch_zip_archive(
            summary=summary,
            items=results,
            output_dir=archive_output_dir,
        )
        summary.zip_archive_path = zip_path
        summary.zip_filename = zip_name
        print(f"[{batch_op_id}] BATCH ZIP ATOMICALLY REGENERATED | {zip_name} ({format_file_size(zip_size)})\n")
    except Exception as zip_err:
        print(f"[{batch_op_id}] WARNING: Batch ZIP regeneration failed: {zip_err}\n")

    return target


def retry_all_failed_batch_items(
    summary: BatchJobSummary,
    results: List[BatchItemResult],
    file_bytes_map: Dict[int, bytes],
    gemini_service: Optional[GeminiService] = None,
    op_id: Optional[str] = None,
    on_retry_start: Optional[Callable[[int, int, str], None]] = None,
    on_stage_change: Optional[Callable[[int, int, str, BatchItemStage], None]] = None,
    on_retry_complete: Optional[Callable[[int, int, BatchItemResult], None]] = None,
    archive_output_dir: Optional[str] = None,
) -> Tuple[BatchJobSummary, List[BatchItemResult]]:
    """
    Retries only eligible failed and partial batch items strictly sequentially.
    Never re-processes already successful items.
    """
    eligible_indices = []
    for r in results:
        is_ret, _ = is_item_retryable(r)
        if is_ret and r.file_index in file_bytes_map:
            eligible_indices.append(r.file_index)

    if not eligible_indices:
        return summary, results

    service = gemini_service or GeminiService()
    batch_op_id = op_id or summary.batch_id
    total_to_retry = len(eligible_indices)

    print(f"[{batch_op_id}] GLOBAL RETRY QUEUE: {total_to_retry} eligible item(s) to retry sequentially.\n")

    for step_idx, item_idx in enumerate(eligible_indices, start=1):
        target = results[item_idx - 1]
        fname = target.original_filename

        if on_retry_start:
            on_retry_start(step_idx, total_to_retry, fname)

        f_bytes = file_bytes_map.get(item_idx, b"")
        retry_single_batch_item(
            item_index=item_idx,
            summary=summary,
            results=results,
            file_bytes=f_bytes,
            gemini_service=service,
            op_id=batch_op_id,
            on_stage_change=on_stage_change,
            archive_output_dir=archive_output_dir,
        )

        if on_retry_complete:
            on_retry_complete(step_idx, total_to_retry, results[item_idx - 1])

        # Gentle inter-item pacing
        if step_idx < total_to_retry:
            time.sleep(INTER_FILE_PACING_SECONDS)

    return summary, results

