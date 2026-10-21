"""Primary Vision Extraction Service (Stage 1: Source-Faithful Raw Extraction)."""

import re
import time
from typing import List, Optional, Tuple, Callable, Any, Dict
from PIL import Image

from models.schemas import (
    ConfidenceLevel,
    PageExtraction,
    RawExtractionResult,
)
from prompts.extraction_prompt import (
    RAW_EXTRACTION_SYSTEM_PROMPT,
    build_raw_extraction_user_prompt,
)
from services.gemini_service import GeminiService
from utils.telemetry import ProgressCallback, log_stage_start, log_stage_success


def parse_extraction_response(response_text: str) -> Tuple[str, ConfidenceLevel, Optional[float], str]:
    """
    Parses metadata and verbatim text from Gemini raw extraction response.
    Returns: (document_type, confidence_level, confidence_score, raw_text)
    """
    doc_type = "unknown"
    confidence_level = ConfidenceLevel.HIGH
    confidence_score = None
    raw_text = response_text

    # Extract METADATA block if present
    metadata_match = re.search(r"=== METADATA ===(.*?)(?:=== RAW_TEXT ===|$)", response_text, re.DOTALL | re.IGNORECASE)
    if metadata_match:
        meta_block = metadata_match.group(1).strip()
        # Parse DOCUMENT_TYPE
        dt_match = re.search(r"DOCUMENT_TYPE:\s*([^\n\r]+)", meta_block, re.IGNORECASE)
        if dt_match:
            doc_type = dt_match.group(1).strip().lower().replace(" ", "_")

        # Parse CONFIDENCE_LEVEL
        cl_match = re.search(r"CONFIDENCE_LEVEL:\s*([^\n\r]+)", meta_block, re.IGNORECASE)
        if cl_match:
            level_str = cl_match.group(1).strip().upper()
            if level_str in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW, ConfidenceLevel.UNAVAILABLE]:
                confidence_level = ConfidenceLevel(level_str)

        # Parse CONFIDENCE_SCORE
        cs_match = re.search(r"CONFIDENCE_SCORE:\s*([0-9.]+)", meta_block, re.IGNORECASE)
        if cs_match:
            try:
                score = float(cs_match.group(1).strip())
                if 0.0 <= score <= 1.0:
                    confidence_score = score
            except ValueError:
                pass

    # Extract RAW_TEXT block
    raw_match = re.search(r"=== RAW_TEXT ===(.*)", response_text, re.DOTALL | re.IGNORECASE)
    if raw_match:
        raw_text = raw_match.group(1).strip()
    elif metadata_match:
        # If metadata block was matched but no explicit === RAW_TEXT === marker
        raw_text = response_text[metadata_match.end():].strip()

    return doc_type, confidence_level, confidence_score, raw_text


def extract_raw_document(
    images: List[Image.Image],
    gemini_service: Optional[GeminiService] = None,
    progress_callback: Optional[ProgressCallback] = None,
    op_id: Optional[str] = None,
) -> RawExtractionResult:
    """
    Coordinates Stage 1 visual extraction across document images.
    Preserves page boundaries and source fidelity.
    Reports real progress and records per-page monotonic durations.
    """
    if not images:
        raise ValueError("No images provided for visual extraction.")

    service = gemini_service or GeminiService()
    total_pages = len(images)
    pages: List[PageExtraction] = []
    combined_texts: List[str] = []

    primary_doc_type = "unknown"
    confidence_levels: List[ConfidenceLevel] = []
    confidence_scores: List[float] = []

    if progress_callback:
        progress_callback("PREPARING", 0.05, {"total_pages": total_pages})

    if op_id:
        log_stage_start(op_id, "VISION OCR", f"Pages: {total_pages}")

    for idx, img in enumerate(images, start=1):
        t_page_start = time.perf_counter()

        if progress_callback:
            progress_callback(
                "PAGE_START",
                (idx - 1) / total_pages,
                {"current_page": idx, "total_pages": total_pages},
            )

        prompt = build_raw_extraction_user_prompt(page_number=idx, total_pages=total_pages)

        if progress_callback:
            progress_callback(
                "CALLING_VISION",
                None,
                {"current_page": idx, "total_pages": total_pages},
            )

        def _on_switch(new_model: str):
            if progress_callback:
                progress_callback("MODEL_SWITCH", None, {"new_model": new_model, "is_fallback": True})

        response_text = service.generate_vision_content(
            image_or_images=img,
            system_instruction=RAW_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.1,
            op_id=op_id,
            on_model_switch=_on_switch,
        )

        if progress_callback:
            progress_callback(
                "PARSING_RESPONSE",
                None,
                {"current_page": idx, "total_pages": total_pages},
            )

        doc_type, conf_level, conf_score, page_raw_text = parse_extraction_response(response_text)
        page_dur = time.perf_counter() - t_page_start

        if op_id:
            log_stage_success(op_id, f"PAGE {idx}/{total_pages}", page_dur)

        if progress_callback:
            progress_callback(
                "PAGE_COMPLETE",
                idx / total_pages,
                {"current_page": idx, "total_pages": total_pages, "page_duration": page_dur},
            )

        if idx == 1:
            primary_doc_type = doc_type

        confidence_levels.append(conf_level)
        if conf_score is not None:
            confidence_scores.append(conf_score)

        pages.append(PageExtraction(
            page_number=idx,
            text=page_raw_text,
            confidence=conf_level,
        ))

        if total_pages > 1:
            combined_texts.append(f"--- Page {idx} ---\n{page_raw_text}")
        else:
            combined_texts.append(page_raw_text)

    if progress_callback:
        progress_callback("FINALIZING", 1.0, {"total_pages": total_pages})

    # Determine overall confidence
    if ConfidenceLevel.LOW in confidence_levels:
        overall_confidence = ConfidenceLevel.LOW
    elif ConfidenceLevel.MEDIUM in confidence_levels:
        overall_confidence = ConfidenceLevel.MEDIUM
    elif ConfidenceLevel.UNAVAILABLE in confidence_levels:
        overall_confidence = ConfidenceLevel.UNAVAILABLE
    else:
        overall_confidence = ConfidenceLevel.HIGH

    overall_score = round(sum(confidence_scores) / len(confidence_scores), 2) if confidence_scores else None
    full_verbatim = "\n\n".join(combined_texts).strip()

    raw_model = getattr(service, "active_model_id", "gemini-3.1-flash-lite")
    model_used = raw_model if isinstance(raw_model, str) else "gemini-3.1-flash-lite"

    return RawExtractionResult(
        verbatim_text=full_verbatim,
        document_type=primary_doc_type,
        confidence_level=overall_confidence,
        confidence_score=overall_score,
        pages=pages,
        page_count=total_pages,
        model_used=model_used,
    )
