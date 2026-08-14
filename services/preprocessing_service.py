"""Preprocessing and quality readiness assessment service."""

from typing import List, Tuple
from PIL import Image

from models.schemas import (
    MetricStatus,
    ReadinessMetric,
    ReadinessReport,
    ReadinessStatus,
)
from utils.image_utils import (
    analyze_image_quality,
    create_preprocessed_copy,
    load_image_safely,
)
from utils.pdf_utils import (
    inspect_pdf,
    render_pdf_pages_adaptively,
)


def assess_document_readiness(
    file_bytes: bytes,
    extension: str,
) -> Tuple[ReadinessReport, List[Image.Image]]:
    """
    Assesses document readiness and renders original PIL Images for preview.
    Returns: (ReadinessReport, list_of_original_images)
    """
    ext = extension.lower()

    if ext == ".pdf":
        inspection = inspect_pdf(file_bytes)
        if not inspection.is_valid:
            error_msg = inspection.error_message or "Invalid PDF document."
            report = ReadinessReport(
                overall_status=ReadinessStatus.LOW_QUALITY,
                readiness_score=0.0,
                readability=ReadinessMetric(
                    name="Readability",
                    status=MetricStatus.POOR,
                    value_display="Unreadable / Corrupt",
                    details=error_msg,
                ),
                warnings=[error_msg],
            )
            return report, []

        # Render PDF pages adaptively
        images = render_pdf_pages_adaptively(file_bytes)
        if not images:
            report = ReadinessReport(
                overall_status=ReadinessStatus.LOW_QUALITY,
                readiness_score=0.0,
                warnings=["PDF contains no renderable pages."],
            )
            return report, []

        # Assess quality on primary page (first page) and aggregate warnings
        primary_report = analyze_image_quality(images[0])
        warnings = primary_report.warnings.copy()

        if inspection.page_count > 1:
            warnings.append(f"Multi-page document: {inspection.page_count} pages detected.")

        return ReadinessReport(
            overall_status=primary_report.overall_status,
            readiness_score=primary_report.readiness_score,
            resolution=primary_report.resolution,
            blur=primary_report.blur,
            contrast=primary_report.contrast,
            brightness=primary_report.brightness,
            skew=primary_report.skew,
            readability=primary_report.readability,
            warnings=warnings,
        ), images

    else:
        # Image document
        image = load_image_safely(file_bytes)
        report = analyze_image_quality(image)
        return report, [image]


def preprocess_document_for_vision(
    original_images: List[Image.Image],
    auto_deskew: bool = True,
    enhance_contrast: bool = True,
) -> Tuple[List[Image.Image], bool]:
    """
    Generates non-destructive preprocessed copies of images for Gemini Vision.
    Leaves original images untouched.
    Returns: (preprocessed_images, any_modifications_made)
    """
    preprocessed_images: List[Image.Image] = []
    any_modified = False

    for img in original_images:
        processed_img, was_mod = create_preprocessed_copy(
            img,
            auto_deskew=auto_deskew,
            enhance_contrast=enhance_contrast,
        )
        preprocessed_images.append(processed_img)
        if was_mod:
            any_modified = True

    return preprocessed_images, any_modified
