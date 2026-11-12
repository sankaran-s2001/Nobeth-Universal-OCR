"""
Pydantic data schemas for Nobeth Universal OCR Bulk Image Processing.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BatchItemStatus(str, Enum):
    """Execution status for an individual batch item."""
    VALID = "VALID"
    INVALID = "INVALID"
    UNSUPPORTED = "UNSUPPORTED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    RETRYING = "RETRYING"
    SUCCESS = "SUCCESS"
    SUCCESS_REVIEWED = "SUCCESS_REVIEWED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class BatchItemStage(str, Enum):
    """Pipeline stages for an individual batch item."""
    QUEUED = "QUEUED"
    VALIDATION = "VALIDATION"
    PREPROCESSING = "PREPROCESSING"
    VISION_OCR = "VISION_OCR"
    JSON_STRUCTURING = "JSON_STRUCTURING"
    JSON_VALIDATION = "JSON_VALIDATION"
    TRACEABILITY = "TRACEABILITY"
    EXPORT = "EXPORT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class BatchPreflightItem(BaseModel):
    """Validation status for an uploaded file before batch execution."""
    filename: str
    file_size: int
    status: BatchItemStatus
    error_message: Optional[str] = None
    relative_path: str = ""
    extension: str = ""


class BatchPreflightSummary(BaseModel):
    """Overall pre-flight validation summary of the selected upload collection."""
    total_selected: int = 0
    valid_count: int = 0
    unsupported_count: int = 0
    invalid_count: int = 0
    total_upload_size: int = 0
    total_upload_size_str: str = "0 B"
    is_processable: bool = False
    items: List[BatchPreflightItem] = Field(default_factory=list)
    error_message: Optional[str] = None


class BatchItemResult(BaseModel):
    """Comprehensive result and telemetry record for a single processed image."""
    file_index: int
    original_filename: str
    relative_path: str = ""
    file_size: int = 0
    status: BatchItemStatus = BatchItemStatus.QUEUED
    current_stage: BatchItemStage = BatchItemStage.QUEUED
    document_type: str = "unknown"
    confidence: str = "HIGH"
    model_used: Optional[str] = None
    readiness_score: Optional[float] = None

    # Granular stage durations in seconds
    validation_duration: Optional[float] = None
    preprocessing_duration: Optional[float] = None
    ocr_duration: Optional[float] = None
    structuring_duration: Optional[float] = None
    export_duration: Optional[float] = None
    total_duration: Optional[float] = None

    # Data artifacts
    raw_text: Optional[str] = None
    original_raw_text: Optional[str] = None
    reviewed_raw_text: Optional[str] = None
    structured_data: Optional[Dict[str, Any]] = None
    traceability: Optional[Dict[str, Any]] = None

    # Review and edit state
    is_reviewed: bool = False
    review_count: int = 0
    last_modified_at: Optional[str] = None

    # Failure, diagnostic, and retry telemetry
    error_message: Optional[str] = None
    error_category: Optional[str] = None
    failed_stage: Optional[str] = None
    is_retryable: bool = True
    retry_count: int = 0
    retry_history: List[Dict[str, Any]] = Field(default_factory=list)

    # Export artifacts
    output_basename: Optional[str] = None
    json_filename: Optional[str] = None
    csv_filename: Optional[str] = None
    txt_filename: Optional[str] = None
    json_content: Optional[str] = None
    csv_content: Optional[str] = None
    txt_content: Optional[str] = None

    @property
    def is_success(self) -> bool:
        """Returns True if the item completed successfully or successfully reviewed."""
        return self.status in [BatchItemStatus.SUCCESS, BatchItemStatus.SUCCESS_REVIEWED]


class BatchJobSummary(BaseModel):
    """Comprehensive summary of a finished or in-progress batch job."""
    batch_id: str
    batch_started_at: str
    batch_finished_at: Optional[str] = None
    total_files: int = 0
    valid_count: int = 0
    completed_count: int = 0
    success_count: int = 0
    partial_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    total_duration: float = 0.0
    average_duration_per_item: float = 0.0
    estimated_remaining_seconds: Optional[float] = None
    zip_archive_path: Optional[str] = None
    zip_filename: Optional[str] = None

