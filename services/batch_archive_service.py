"""
Batch Archive Service: Builds organized ZIP packages, manifests, and documentation for bulk OCR jobs.
"""

import csv
import io
import json
import os
import re
import tempfile
import time
import zipfile
from datetime import datetime
from typing import List, Optional, Tuple

from models.batch_schemas import BatchItemResult, BatchItemStatus, BatchJobSummary


def sanitize_filename_stem(filename: str) -> str:
    """
    Sanitizes a filename to create a clean, path-traversal safe stem.
    Preserves alphanumeric characters, dashes, and underscores.
    """
    basename = os.path.basename(filename)
    stem, _ = os.path.splitext(basename)
    # Replace spaces and punctuation with underscores, collapse multiple underscores
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", stem)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "document"


def generate_batch_zip_filename(
    batch_id: str,
    total_files: int,
    generation_date: Optional[datetime] = None,
) -> str:
    """
    Generates standardized ZIP archive filename.
    Format: Nobeth_OCR_Batch_<YYYY-MM-DD>_<count>_files_<batch_id>.zip
    """
    dt = generation_date or datetime.now()
    date_str = dt.strftime("%Y-%m-%d")
    clean_id = re.sub(r"[^A-Za-z0-9]", "", batch_id).upper() or "BATCH"
    return f"Nobeth_OCR_Batch_{date_str}_{total_files}_files_{clean_id}.zip"


def generate_manifest_json(summary: BatchJobSummary, items: List[BatchItemResult]) -> str:
    """
    Generates structured batch manifest in JSON format.
    Sanitized: Contains zero sensitive API keys or full raw text payloads.
    """
    manifest_data = {
        "batch_id": summary.batch_id,
        "created_at": summary.batch_started_at,
        "completed_at": summary.batch_finished_at,
        "summary": {
            "total_files": summary.total_files,
            "valid_files": summary.valid_count,
            "successful_files": summary.success_count,
            "partial_files": summary.partial_count,
            "failed_files": summary.failed_count,
            "skipped_files": summary.skipped_count,
            "total_duration_seconds": round(summary.total_duration, 3),
            "average_duration_seconds": round(summary.average_duration_per_item, 3),
        },
        "records": [
            {
                "file_index": item.file_index,
                "original_filename": item.original_filename,
                "relative_path": item.relative_path,
                "file_size_bytes": item.file_size,
                "status": item.status.value,
                "is_reviewed": getattr(item, "is_reviewed", False),
                "review_count": getattr(item, "review_count", 0),
                "retry_count": getattr(item, "retry_count", 0),
                "last_modified_at": getattr(item, "last_modified_at", None),
                "document_type": item.document_type,
                "confidence": item.confidence,
                "model_used": item.model_used,
                "readiness_score": item.readiness_score,
                "durations": {
                    "validation_sec": round(item.validation_duration or 0.0, 3),
                    "preprocessing_sec": round(item.preprocessing_duration or 0.0, 3),
                    "ocr_sec": round(item.ocr_duration or 0.0, 3),
                    "structuring_sec": round(item.structuring_duration or 0.0, 3),
                    "export_sec": round(item.export_duration or 0.0, 3),
                    "total_sec": round(item.total_duration or 0.0, 3),
                },
                "generated_files": {
                    "json": item.json_filename,
                    "csv": item.csv_filename,
                    "txt": item.txt_filename,
                },
                "failed_stage": item.failed_stage,
                "error_category": item.error_category,
                "error_message": item.error_message,
                "retry_history": getattr(item, "retry_history", []),
            }
            for item in items
        ],
    }
    return json.dumps(manifest_data, indent=2, ensure_ascii=False)


def generate_manifest_csv(summary: BatchJobSummary, items: List[BatchItemResult]) -> str:
    """
    Generates tabular batch manifest in CSV format.
    """
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    headers = [
        "Batch ID",
        "Index",
        "Original Filename",
        "Relative Path",
        "Status",
        "Reviewed",
        "Review Count",
        "Retry Count",
        "Document Type",
        "Confidence",
        "Model Used",
        "Readiness Score (%)",
        "OCR Duration (s)",
        "Structuring Duration (s)",
        "Total Duration (s)",
        "JSON File",
        "CSV File",
        "TXT File",
        "Failed Stage",
        "Error Category",
        "Error Message",
    ]
    writer.writerow(headers)

    for item in items:
        writer.writerow([
            summary.batch_id,
            item.file_index,
            item.original_filename,
            item.relative_path,
            item.status.value,
            "YES" if getattr(item, "is_reviewed", False) else "NO",
            getattr(item, "review_count", 0),
            getattr(item, "retry_count", 0),
            item.document_type,
            item.confidence,
            item.model_used or "",
            f"{item.readiness_score:.1f}" if item.readiness_score is not None else "",
            f"{item.ocr_duration:.3f}" if item.ocr_duration is not None else "",
            f"{item.structuring_duration:.3f}" if item.structuring_duration is not None else "",
            f"{item.total_duration:.3f}" if item.total_duration is not None else "",
            item.json_filename or "",
            item.csv_filename or "",
            item.txt_filename or "",
            item.failed_stage or "",
            item.error_category or "",
            item.error_message or "",
        ])

    return output.getvalue()


def generate_batch_readme(summary: BatchJobSummary, archive_root_dir: str) -> str:
    """
    Generates clean, human-readable README.txt for the batch ZIP archive.
    """
    return f"""========================================================================
NOBETH UNIVERSAL OCR | BATCH PROCESSING ARCHIVE
========================================================================

Batch ID        : {summary.batch_id}
Started At      : {summary.batch_started_at}
Finished At     : {summary.batch_finished_at or 'In Progress'}
Total Files     : {summary.total_files}
Successful Files: {summary.success_count}
Partial Files   : {summary.partial_count}
Failed Files    : {summary.failed_count}
Skipped Files   : {summary.skipped_count}
Total Duration  : {summary.total_duration:.2f} seconds
Average Duration: {summary.average_duration_per_item:.2f} seconds/item

------------------------------------------------------------------------
ARCHIVE DIRECTORY STRUCTURE
------------------------------------------------------------------------

{archive_root_dir}/
│
├── batch_manifest.csv   <- Tabular log of every file, timing, and status
├── batch_manifest.json  <- Structured JSON manifest with full telemetry
├── README.txt           <- This guide
│
├── successful/          <- Fully processed files (Vision OCR + Dynamic JSON)
│   ├── <index>_<stem>/
│   │   ├── <stem>.json  <- Source-faithful structured JSON data
│   │   ├── <stem>.csv   <- Tabular normalized CSV data
│   │   └── <stem>.txt   <- Verbatim source text extraction
│   └── ...
│
├── partial/             <- Files where Stage 1 succeeded but Stage 2 failed
│   ├── <index>_<stem>/
│   │   └── <stem>.txt   <- Verbatim source text (Stage 1 preserved)
│   └── ...
│
└── failed/              <- Files with validation, decoding, or API failures
    ├── <index>_<stem>_error.json <- Structured diagnostic failure report
    └── <index>_<stem>_error.txt  <- Human-readable error description

------------------------------------------------------------------------
ABOUT NOBETH UNIVERSAL OCR
------------------------------------------------------------------------
Built with Google Gemini Vision models and Python.
Nobeth Analytics - Advanced AI Document Intelligence & Automation.
"""


def build_batch_zip_archive(
    summary: BatchJobSummary,
    items: List[BatchItemResult],
    output_dir: Optional[str] = None,
) -> Tuple[str, str, int]:
    """
    Safely and atomically creates the complete batch ZIP archive on disk.
    Builds the archive in a temporary file first, verifies integrity, then atomically replaces destination.
    Returns: (zip_file_path, zip_filename, file_size_bytes)
    """
    dt = datetime.now()
    zip_filename = generate_batch_zip_filename(summary.batch_id, summary.total_files, dt)

    target_dir = output_dir or tempfile.gettempdir()
    os.makedirs(target_dir, exist_ok=True)
    zip_path = os.path.join(target_dir, zip_filename)
    temp_zip_path = os.path.join(target_dir, f"{zip_filename}.{os.getpid()}_{int(time.time()*1000)}.tmp")

    # Clean stem for root directory inside ZIP
    root_folder = zip_filename.rsplit(".", 1)[0]

    try:
        with zipfile.ZipFile(temp_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # 1. Add batch manifest (JSON & CSV)
            manifest_json = generate_manifest_json(summary, items)
            zf.writestr(f"{root_folder}/batch_manifest.json", manifest_json.encode("utf-8"))

            manifest_csv = generate_manifest_csv(summary, items)
            zf.writestr(f"{root_folder}/batch_manifest.csv", manifest_csv.encode("utf-8"))

            # 2. Add README.txt
            readme_txt = generate_batch_readme(summary, root_folder)
            zf.writestr(f"{root_folder}/README.txt", readme_txt.encode("utf-8"))

            # 3. Add individual file results
            for item in items:
                idx_str = f"{item.file_index:03d}"
                stem = item.output_basename or sanitize_filename_stem(item.original_filename)

                if item.status in [BatchItemStatus.SUCCESS, BatchItemStatus.SUCCESS_REVIEWED]:
                    folder_name = f"{root_folder}/successful/{idx_str}_{stem}"
                    if item.json_content:
                        zf.writestr(f"{folder_name}/{stem}.json", item.json_content.encode("utf-8"))
                    if item.csv_content:
                        zf.writestr(f"{folder_name}/{stem}.csv", item.csv_content.encode("utf-8"))
                    if item.txt_content:
                        zf.writestr(f"{folder_name}/{stem}.txt", item.txt_content.encode("utf-8"))

                elif item.status == BatchItemStatus.PARTIAL:
                    folder_name = f"{root_folder}/partial/{idx_str}_{stem}"
                    if item.txt_content:
                        zf.writestr(f"{folder_name}/{stem}.txt", item.txt_content.encode("utf-8"))
                    # Include error report for why Stage 2 failed
                    err_dict = {
                        "original_filename": item.original_filename,
                        "status": "PARTIAL",
                        "failed_stage": item.failed_stage or "JSON_STRUCTURING",
                        "error_category": item.error_category or "STRUCTURING_FAILURE",
                        "error_message": item.error_message,
                    }
                    zf.writestr(
                        f"{folder_name}/{stem}_structuring_error.json",
                        json.dumps(err_dict, indent=2).encode("utf-8"),
                    )

                elif item.status in [BatchItemStatus.FAILED, BatchItemStatus.INVALID, BatchItemStatus.UNSUPPORTED]:
                    folder_name = f"{root_folder}/failed"
                    err_dict = {
                        "file_index": item.file_index,
                        "original_filename": item.original_filename,
                        "status": item.status.value,
                        "failed_stage": item.failed_stage,
                        "error_category": item.error_category,
                        "error_message": item.error_message,
                        "total_duration_sec": item.total_duration,
                    }
                    zf.writestr(
                        f"{folder_name}/{idx_str}_{stem}_error.json",
                        json.dumps(err_dict, indent=2).encode("utf-8"),
                    )
                    zf.writestr(
                        f"{folder_name}/{idx_str}_{stem}_error.txt",
                        f"File: {item.original_filename}\nStatus: {item.status.value}\nStage: {item.failed_stage}\nCategory: {item.error_category}\nError: {item.error_message}\n".encode("utf-8"),
                    )

        # Integrity verification
        with zipfile.ZipFile(temp_zip_path, "r") as zf_test:
            bad_file = zf_test.testzip()
            if bad_file:
                raise zipfile.BadZipFile(f"Corrupt ZIP member: {bad_file}")

        # Atomic replacement
        os.replace(temp_zip_path, zip_path)
    except Exception:
        if os.path.exists(temp_zip_path):
            try:
                os.remove(temp_zip_path)
            except Exception:
                pass
        raise

    file_size = os.path.getsize(zip_path)
    return zip_path, zip_filename, file_size
