"""Dynamic Universal Structuring Service (Stage 2: Structured Understanding)."""

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
) -> StructuredExtractionResult:
    """
    Converts reviewed raw document text into dynamic structured JSON using Gemini.
    Validates output structure and guarantees valid result.
    """
    if not reviewed_raw_text or not reviewed_raw_text.strip():
        raise ValueError("Cannot structure empty raw text.")

    service = gemini_service or GeminiService()
    prompt = build_structuring_user_prompt(
        reviewed_raw_text=reviewed_raw_text,
        document_type_hint=document_type_hint,
    )

    response_text = service.generate_text_content(
        system_instruction=STRUCTURING_SYSTEM_PROMPT,
        user_prompt=prompt,
        temperature=0.0,
    )

    parsed_data, is_valid, val_msg = parse_and_validate_json(response_text)

    if not parsed_data or not isinstance(parsed_data, dict):
        return StructuredExtractionResult(
            document_type=document_type_hint,
            data={"raw_text": reviewed_raw_text, "error": "Structured conversion failed to produce valid JSON dictionary."},
            traceability=[],
            confidence_level=ConfidenceLevel.LOW,
            is_valid=False,
            validation_message=val_msg or "Failed to parse structured JSON from Gemini response.",
        )

    # Inferred document type from structured data or fallback to hint
    doc_type = str(parsed_data.get("document_type", document_type_hint)).lower().replace(" ", "_")

    # Inferred confidence level from structured data or default to HIGH
    conf_str = str(parsed_data.get("confidence_level", "HIGH")).upper()
    conf_level = ConfidenceLevel(conf_str) if conf_str in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW, ConfidenceLevel.UNAVAILABLE] else ConfidenceLevel.HIGH

    # Extract traceability
    traces = extract_field_traceability(parsed_data, reviewed_raw_text)

    return StructuredExtractionResult(
        document_type=doc_type,
        data=parsed_data,
        traceability=traces,
        confidence_level=conf_level,
        is_valid=is_valid,
        validation_message=val_msg,
    )
