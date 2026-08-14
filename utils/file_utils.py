"""File handling, format detection, and size validation utilities."""

import os
from typing import Optional, Set, Tuple

# Supported file extensions
IMAGE_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tiff", ".tif"}
DOCUMENT_EXTENSIONS: Set[str] = {".pdf"}
SUPPORTED_EXTENSIONS: Set[str] = IMAGE_EXTENSIONS.union(DOCUMENT_EXTENSIONS)

# MIME type mappings
MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".pdf": "application/pdf",
}

SUPPORTED_MIME_TYPES = set(MIME_MAP.values())

# Magic byte signatures for robust format detection
MAGIC_SIGNATURES = [
    (b"\xff\xd8\xff", ".jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", ".png", "image/png"),
    (b"RIFF", ".webp", "image/webp"),  # RIFF....WEBP
    (b"II*\x00", ".tiff", "image/tiff"),  # Little-endian TIFF
    (b"MM\x00*", ".tiff", "image/tiff"),  # Big-endian TIFF
    (b"%PDF-", ".pdf", "application/pdf"),
    (b"ftypheic", ".heic", "image/heic"),
    (b"ftypmif1", ".heic", "image/heic"),
    (b"ftypmsf1", ".heic", "image/heic"),
    (b"ftypheix", ".heic", "image/heic"),
]


def get_max_file_size_bytes() -> int:
    """Returns max upload size in bytes from environment or default 50 MB."""
    max_mb_str = os.getenv("MAX_FILE_SIZE_MB", "50")
    try:
        max_mb = float(max_mb_str)
    except ValueError:
        max_mb = 50.0
    return int(max_mb * 1024 * 1024)


def format_file_size(size_in_bytes: int) -> str:
    """Formats byte count to human-readable string (e.g. '2.4 MB', '450 KB')."""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} KB"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{size_in_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_in_bytes / (1024 * 1024 * 1024):.2f} GB"


def detect_file_format(filename: str, file_bytes: Optional[bytes] = None) -> Tuple[str, str, bool]:
    """
    Detects file extension and MIME type using filename and magic bytes.
    Returns: (normalized_extension, mime_type, is_supported)
    """
    _, ext = os.path.splitext(filename.lower())

    # Check magic bytes if available
    detected_ext = ext
    detected_mime = MIME_MAP.get(ext, "application/octet-stream")

    if file_bytes and len(file_bytes) >= 12:
        header = file_bytes[:12]
        # Check PDF header
        if header.startswith(b"%PDF-"):
            detected_ext = ".pdf"
            detected_mime = "application/pdf"
        # Check JPEG header
        elif header.startswith(b"\xff\xd8\xff"):
            detected_ext = ".jpg" if ext not in [".jpg", ".jpeg"] else ext
            detected_mime = "image/jpeg"
        # Check PNG header
        elif header.startswith(b"\x89PNG\r\n\x1a\n"):
            detected_ext = ".png"
            detected_mime = "image/png"
        # Check WEBP
        elif header.startswith(b"RIFF") and b"WEBP" in file_bytes[:16]:
            detected_ext = ".webp"
            detected_mime = "image/webp"
        # Check TIFF
        elif header.startswith(b"II*\x00") or header.startswith(b"MM\x00*"):
            detected_ext = ".tiff" if ext not in [".tiff", ".tif"] else ext
            detected_mime = "image/tiff"
        # Check HEIC ftyp
        elif b"ftyp" in header[4:8] and any(sig in file_bytes[:32] for sig in [b"heic", b"mif1", b"msf1", b"heix"]):
            detected_ext = ".heic"
            detected_mime = "image/heic"

    is_supported = detected_ext in SUPPORTED_EXTENSIONS
    return detected_ext, detected_mime, is_supported


def get_mime_type(filename: str, file_bytes: Optional[bytes] = None) -> str:
    """Returns the MIME type string for a given file."""
    _, mime, _ = detect_file_format(filename, file_bytes)
    return mime


def validate_file_size(size_in_bytes: int) -> Tuple[bool, Optional[str]]:
    """Checks if file size is within limits and not empty."""
    if size_in_bytes <= 0:
        return False, "Uploaded file is empty (0 bytes)."

    max_bytes = get_max_file_size_bytes()
    if size_in_bytes > max_bytes:
        max_mb = max_bytes / (1024 * 1024)
        return False, f"File size ({format_file_size(size_in_bytes)}) exceeds limit of {max_mb:.0f} MB."

    return True, None
