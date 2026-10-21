import time
from typing import Any, Dict, List, Optional
from models.schemas import (
    ConfidenceLevel,
    FieldTrace,
    StructuredExtractionResult,
)
from prompts.structuring_prompt import (
    STRUCTURING_SYSTEM_PROMPT,
    build_structuring_user_prompt,
)
from services.gemini_service import GeminiService
from utils.telemetry import ProgressCallback, log_stage_start, log_stage_success
from utils.validation import parse_and_validate_json


def extract_field_traceability(data: Dict[str, Any], raw_text: str) -> List[FieldTrace]:
    """
    Extracts traceability links between structured fields and raw occurrences.
    """
    traces: List[FieldTrace] = []

    def _traverse(obj: Any, prefix: str = ""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                curr_key = f"{prefix}.{k}" if prefix else k
                if k in ["document_type", "confidence_level", "traceability"]:
                    continue
                if isinstance(v, (str, int, float, bool)) and v is not None:
                    # Check if str(v) appears in raw_text
                    v_str = str(v)
                    raw_match = v_str if v_str in raw_text else None
                    traces.append(FieldTrace(
                        field_name=curr_key,
                        raw_value=raw_match,
                        structured_value=v,
                        confidence=ConfidenceLevel.HIGH if raw_match else ConfidenceLevel.MEDIUM,
                    ))
                elif isinstance(v, (dict, list)):
                    _traverse(v, curr_key)
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                curr_key = f"{prefix}[{idx}]"
                if isinstance(item, (str, int, float, bool)) and item is not None:
                    item_str = str(item)
                    raw_match = item_str if item_str in raw_text else None
                    traces.append(FieldTrace(
                        field_name=curr_key,
                        raw_value=raw_match,
                        structured_value=item,
                        confidence=ConfidenceLevel.HIGH if raw_match else ConfidenceLevel.MEDIUM,
                    ))
                elif isinstance(item, (dict, list)):
                    _traverse(item, curr_key)

    _traverse(data)
    return traces


def structure_raw_extraction(
    reviewed_raw_text: str,
    document_type_hint: str = "unknown",
    gemini_service: Optional[GeminiService] = None,
    progress_callback: Optional[ProgressCallback] = None,
    op_id: Optional[str] = None,
) -> StructuredExtractionResult:
    """
    Converts reviewed raw document text into dynamic structured JSON using Gemini.
    Validates output structure and guarantees valid result.
    Tracks high-resolution durations for API wait, JSON parsing, and traceability.
    """
    if not reviewed_raw_text or not reviewed_raw_text.strip():
        raise ValueError("Cannot structure empty raw text.")

    if progress_callback:
        progress_callback("PREPARING_TEXT", 0.10, {"document_type_hint": document_type_hint})

    if op_id:
        log_stage_start(op_id, "JSON STRUCTURING", f"Type hint: {document_type_hint}")

    service = gemini_service or GeminiService()
    prompt = build_structuring_user_prompt(
        reviewed_raw_text=reviewed_raw_text,
        document_type_hint=document_type_hint,
    )

    if progress_callback:
        progress_callback("SENDING_PROMPT", 0.30, {})

    def _on_switch(new_model: str):
        if progress_callback:
            progress_callback("MODEL_SWITCH", None, {"new_model": new_model, "is_fallback": True})

    t_api_start = time.perf_counter()
    response_text = service.generate_text_content(
        system_instruction=STRUCTURING_SYSTEM_PROMPT,
        user_prompt=prompt,
        temperature=0.0,
        op_id=op_id,
        on_model_switch=_on_switch,
    )
    api_dur = time.perf_counter() - t_api_start

    if op_id:
        log_stage_success(op_id, "GEMINI STRUCTURING", api_dur)

    if progress_callback:
        progress_callback("PARSING_JSON", 0.70, {})

    t_parse_start = time.perf_counter()
    parsed_data, is_valid, val_msg = parse_and_validate_json(response_text)
    parse_dur = time.perf_counter() - t_parse_start

    if op_id:
        log_stage_success(op_id, "JSON VALIDATION", parse_dur, "Valid" if is_valid else "Invalid")

    raw_model = getattr(service, "active_model_id", "gemini-3.1-flash-lite")
    model_used = raw_model if isinstance(raw_model, str) else "gemini-3.1-flash-lite"

    if not parsed_data or not isinstance(parsed_data, dict):
        if progress_callback:
            progress_callback("COMPLETE", 1.0, {"is_valid": False})
        return StructuredExtractionResult(
            document_type=document_type_hint,
            data={"raw_text": reviewed_raw_text, "error": "Structured conversion failed to produce valid JSON dictionary."},
            traceability=[],
            confidence_level=ConfidenceLevel.LOW,
            is_valid=False,
            validation_message=val_msg or "Failed to parse structured JSON from Gemini response.",
            model_used=model_used,
        )

    # Inferred document type from structured data or fallback to hint
    doc_type = str(parsed_data.get("document_type", document_type_hint)).lower().replace(" ", "_")

    # Inferred confidence level from structured data or default to HIGH
    conf_str = str(parsed_data.get("confidence_level", "HIGH")).upper()
    conf_level = ConfidenceLevel(conf_str) if conf_str in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW, ConfidenceLevel.UNAVAILABLE] else ConfidenceLevel.HIGH

    if progress_callback:
        progress_callback("EXTRACTING_TRACEABILITY", 0.85, {})

    t_trace_start = time.perf_counter()
    traces = extract_field_traceability(parsed_data, reviewed_raw_text)
    trace_dur = time.perf_counter() - t_trace_start

    if op_id:
        log_stage_success(op_id, "TRACEABILITY", trace_dur, f"{len(traces)} fields mapped")

    if progress_callback:
        progress_callback("COMPLETE", 1.0, {"is_valid": is_valid})

    return StructuredExtractionResult(
        document_type=doc_type,
        data=parsed_data,
        traceability=traces,
        confidence_level=conf_level,
        is_valid=is_valid,
        validation_message=val_msg,
        model_used=model_used,
    )
