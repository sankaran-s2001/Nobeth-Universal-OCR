"""Pydantic data schemas for Nobeth Universal OCR."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MetricStatus(str, Enum):
    """Quality metric rating levels."""
    GOOD = "GOOD"
    ADEQUATE = "ADEQUATE"
    WARNING = "WARNING"
    POOR = "POOR"
    UNCERTAIN = "UNCERTAIN"


class ReadinessStatus(str, Enum):
    """Overall document readiness classification."""
    READY = "READY"
    READY_WITH_WARNINGS = "READY WITH WARNINGS"
    LOW_QUALITY = "LOW QUALITY"


class ConfidenceLevel(str, Enum):
    """Meaningful extraction confidence indicators."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNAVAILABLE = "UNAVAILABLE"


class ReadinessMetric(BaseModel):
    """Individual quality check metric."""
    name: str = Field(description="Display name of the metric (e.g. Resolution, Blur, Contrast)")
    status: MetricStatus = Field(default=MetricStatus.GOOD, description="Status rating")
    value_display: str = Field(description="Formatted human-readable value (e.g. '300 DPI', 'Low Blur')")
    details: str = Field(default="", description="Diagnostic details or recommendations")


class ReadinessReport(BaseModel):
    """Comprehensive readiness assessment report for uploaded document."""
    overall_status: ReadinessStatus = Field(default=ReadinessStatus.READY)
    readiness_score: float = Field(default=100.0, ge=0.0, le=100.0, description="Overall readiness score (0-100%)")
    resolution: ReadinessMetric = Field(default_factory=lambda: ReadinessMetric(name="Resolution", status=MetricStatus.GOOD, value_display="Good"))
    blur: ReadinessMetric = Field(default_factory=lambda: ReadinessMetric(name="Blur", status=MetricStatus.GOOD, value_display="Low"))
    contrast: ReadinessMetric = Field(default_factory=lambda: ReadinessMetric(name="Contrast", status=MetricStatus.GOOD, value_display="Good"))
    brightness: ReadinessMetric = Field(default_factory=lambda: ReadinessMetric(name="Brightness", status=MetricStatus.GOOD, value_display="Balanced"))
    skew: ReadinessMetric = Field(default_factory=lambda: ReadinessMetric(name="Orientation / Skew", status=MetricStatus.GOOD, value_display="Aligned"))
    readability: ReadinessMetric = Field(default_factory=lambda: ReadinessMetric(name="Readability", status=MetricStatus.GOOD, value_display="Clear"))
    warnings: List[str] = Field(default_factory=list, description="Actionable warnings or observations")


class PageExtraction(BaseModel):
    """Raw extraction result for an individual page."""
    page_number: int = Field(ge=1)
    text: str = Field(default="")
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.HIGH)


class RawExtractionResult(BaseModel):
    """Result of Stage 1: Gemini Vision Source-Faithful Raw Extraction."""
    verbatim_text: str = Field(description="Exact source-faithful extracted text")
    document_type: str = Field(default="unknown", description="Automatically inferred document type")
    confidence_level: ConfidenceLevel = Field(default=ConfidenceLevel.HIGH)
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pages: List[PageExtraction] = Field(default_factory=list)
    page_count: int = Field(default=1, ge=1)
    notes: Optional[str] = Field(default=None)


class FieldTrace(BaseModel):
    """Traceability link between raw extracted text and normalized structured value."""
    field_name: str
    raw_value: Optional[str] = None
    structured_value: Any = None
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.HIGH)
    source_page: Optional[int] = None


class StructuredExtractionResult(BaseModel):
    """Result of Stage 2: Dynamic AI Structured Understanding."""
    document_type: str = Field(default="unknown")
    data: Dict[str, Any] = Field(default_factory=dict, description="Dynamic JSON document representation")
    traceability: List[FieldTrace] = Field(default_factory=list)
    confidence_level: ConfidenceLevel = Field(default=ConfidenceLevel.HIGH)
    is_valid: bool = Field(default=True)
    validation_message: Optional[str] = None


class ExportBundle(BaseModel):
    """Export artifacts in multiple formats."""
    base_filename: str
    json_content: str
    csv_content: str
    txt_content: str
