"""Validation and resilient JSON parsing utilities."""

import json
import re
from typing import Any, Dict, Optional, Tuple

from utils.file_utils import (
    detect_file_format,
    validate_file_size,
)


def validate_upload_bytes(filename: str, file_bytes: bytes) -> Tuple[bool, Optional[str], str]:
    """
    Validates uploaded file bytes, format, and size.
    Returns: (is_valid, error_message, detected_extension)
    """
    if not file_bytes or len(file_bytes) == 0:
        return False, "Uploaded file is empty (0 bytes).", ""

    ext, mime, is_supported = detect_file_format(filename, file_bytes)
    if not is_supported:
        return (
            False,
            f"Unsupported file format '{ext}'. Supported formats: JPG, PNG, WEBP, HEIC, TIFF, PDF.",
            ext,
        )

    size_ok, size_err = validate_file_size(len(file_bytes))
    if not size_ok:
        return False, size_err, ext

    return True, None, ext


def clean_json_markdown(text: str) -> str:
    """Strips markdown code block wrappers from JSON string."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def attempt_json_repair(text: str) -> Optional[Dict[str, Any]]:
    """
    Attempts heuristic repair of slightly malformed JSON strings.
    """
    cleaned = clean_json_markdown(text)

    # 1. Try direct parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
        elif isinstance(data, list):
            return {"items": data}
    except Exception:
        pass

    # 2. Extract substring between first '{' and last '}'
    start_brace = cleaned.find("{")
    end_brace = cleaned.rfind("}")
    if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
        candidate = cleaned[start_brace : end_brace + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        # 3. Clean common LLM formatting issues: trailing commas before '}' or ']'
        repaired = re.sub(r",\s*([\]}])", r"\1", candidate)
        try:
            data = json.loads(repaired)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


def parse_and_validate_json(raw_json_str: str) -> Tuple[Optional[Dict[str, Any]], bool, Optional[str]]:
    """
    Parses and validates a JSON string.
    Returns: (parsed_data, is_valid, error_or_warning_message)
    """
    if not raw_json_str or not raw_json_str.strip():
        return None, False, "JSON content is empty."

    cleaned = clean_json_markdown(raw_json_str)

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data, True, None
        elif isinstance(data, list):
            return {"data": data}, True, "Notice: Root array wrapped in object container."
        else:
            return {"value": data}, True, "Notice: Primitive value wrapped in object container."
    except json.JSONDecodeError as e:
        # Attempt repair
        repaired = attempt_json_repair(raw_json_str)
        if repaired is not None:
            return repaired, True, "Notice: Minor syntax inconsistencies were automatically repaired."
        return None, False, f"Invalid JSON syntax: line {e.lineno}, col {e.colno} ({e.msg})"
    except Exception as e:
        return None, False, f"Failed to parse JSON: {str(e)}"
