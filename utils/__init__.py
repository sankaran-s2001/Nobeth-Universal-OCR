"""Utilities package for Nobeth Universal OCR."""

from utils.file_utils import (
    SUPPORTED_EXTENSIONS,
    SUPPORTED_MIME_TYPES,
    detect_file_format,
    format_file_size,
    get_mime_type,
    validate_file_size,
)
from utils.image_utils import (
    load_image_safely,
    analyze_image_quality,
    create_preprocessed_copy,
    pil_to_opencv,
    opencv_to_pil,
)
from utils.pdf_utils import (
    inspect_pdf,
    render_pdf_pages_adaptively,
    PdfInspectionResult,
)
from utils.validation import (
    validate_upload_bytes,
    parse_and_validate_json,
)

__all__ = [
    "SUPPORTED_EXTENSIONS",
    "SUPPORTED_MIME_TYPES",
    "detect_file_format",
    "format_file_size",
    "get_mime_type",
    "validate_file_size",
    "load_image_safely",
    "analyze_image_quality",
    "create_preprocessed_copy",
    "pil_to_opencv",
    "opencv_to_pil",
    "inspect_pdf",
    "render_pdf_pages_adaptively",
    "PdfInspectionResult",
    "validate_upload_bytes",
    "parse_and_validate_json",
]
