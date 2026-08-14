"""Prompts package for Nobeth Universal OCR."""

from prompts.extraction_prompt import (
    RAW_EXTRACTION_SYSTEM_PROMPT,
    build_raw_extraction_user_prompt,
)
from prompts.structuring_prompt import (
    STRUCTURING_SYSTEM_PROMPT,
    build_structuring_user_prompt,
)

__all__ = [
    "RAW_EXTRACTION_SYSTEM_PROMPT",
    "build_raw_extraction_user_prompt",
    "STRUCTURING_SYSTEM_PROMPT",
    "build_structuring_user_prompt",
]
