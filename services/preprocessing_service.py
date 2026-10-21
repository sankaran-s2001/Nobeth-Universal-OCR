import time
from typing import List, Optional, Tuple
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
from utils.telemetry import ProgressCallback, log_stage_start, log_stage_success


def assess_document_readiness(
    file_bytes: bytes,
    extension: str,
    progress_callback: Optional[ProgressCallback] = None,
    op_id: Optional[str] = None,
) -> Tuple[ReadinessReport, List[Image.Image]]:
    """
    Assesses document readiness and renders original PIL Images for preview.
    Measures duration for rendering and readiness diagnostics.
    Returns: (ReadinessReport, list_of_original_images)
    """
    ext = extension.lower()

    if ext == ".pdf":
        if progress_callback:
            progress_callback("INSPECTING_PDF", 0.15, {})

        t_inspect = time.perf_counter()
        inspection = inspect_pdf(file_bytes)
        inspect_dur = time.perf_counter() - t_inspect

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

        if progress_callback:
            progress_callback("RENDERING_PDF_PAGES", 0.45, {"pages": inspection.page_count})

        # Render PDF pages adaptively
        t_render = time.perf_counter()
        images = render_pdf_pages_adaptively(file_bytes)
        render_dur = time.perf_counter() - t_render

        if op_id:
            log_stage_success(op_id, "PDF RENDERING", render_dur, f"{len(images)} page(s)")

        if not images:
            report = ReadinessReport(
                overall_status=ReadinessStatus.LOW_QUALITY,
                readiness_score=0.0,
                warnings=["PDF contains no renderable pages."],
            )
            return report, []

        if progress_callback:
            progress_callback("ANALYZING_READINESS", 0.80, {})

        # Assess quality on primary page (first page) and aggregate warnings
        t_diag = time.perf_counter()
        primary_report = analyze_image_quality(images[0])
        diag_dur = time.perf_counter() - t_diag

        if op_id:
            log_stage_success(op_id, "READINESS DIAGNOSTICS", diag_dur, f"Score: {primary_report.readiness_score:.0f}%")

        warnings = primary_report.warnings.copy()
        if inspection.page_count > 1:
            warnings.append(f"Multi-page document: {inspection.page_count} pages detected.")

        if progress_callback:
            progress_callback("PREPARATION_COMPLETE", 1.0, {"score": primary_report.readiness_score})

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
        if progress_callback:
            progress_callback("DECODING_IMAGE", 0.20, {})

        t_load = time.perf_counter()
        image = load_image_safely(file_bytes)
        load_dur = time.perf_counter() - t_load

        if op_id:
            log_stage_success(op_id, "IMAGE DECODING", load_dur, f"{image.width}x{image.height} {image.format}")

        if progress_callback:
            progress_callback("ANALYZING_READINESS", 0.70, {})

        t_diag = time.perf_counter()
        report = analyze_image_quality(image)
        diag_dur = time.perf_counter() - t_diag

        if op_id:
            log_stage_success(op_id, "READINESS DIAGNOSTICS", diag_dur, f"Score: {report.readiness_score:.0f}%")

        if progress_callback:
            progress_callback("PREPARATION_COMPLETE", 1.0, {"score": report.readiness_score})

        return report, [image]


def preprocess_document_for_vision(
    original_images: List[Image.Image],
    auto_deskew: bool = True,
    enhance_contrast: bool = True,
    op_id: Optional[str] = None,
) -> Tuple[List[Image.Image], bool]:
    """
    Generates non-destructive preprocessed copies of images for Gemini Vision.
    Leaves original images untouched.
    Returns: (preprocessed_images, any_modifications_made)
    """
    t0 = time.perf_counter()
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

    prep_dur = time.perf_counter() - t0
    if op_id:
        dim_info = f"{preprocessed_images[0].width}x{preprocessed_images[0].height}" if preprocessed_images else "0"
        log_stage_success(op_id, "IMAGE PREPROCESSING", prep_dur, f"{len(preprocessed_images)} img(s), max: {dim_info}")

    return preprocessed_images, any_modified
