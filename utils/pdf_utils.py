"""PDF inspection and adaptive multi-page rendering utilities using PyMuPDF."""

import io
from typing import List, Optional, Tuple
from PIL import Image
import fitz  # PyMuPDF
from pydantic import BaseModel, Field


class PdfInspectionResult(BaseModel):
    """Result of PDF file validation and inspection."""
    page_count: int = 0
    is_encrypted: bool = False
    is_valid: bool = True
    error_message: Optional[str] = None
    page_dimensions: List[Tuple[float, float]] = Field(default_factory=list)


def inspect_pdf(pdf_bytes: bytes) -> PdfInspectionResult:
    """
    Inspects a PDF byte stream for encryption, page count, and structural integrity.
    """
    if not pdf_bytes or len(pdf_bytes) < 8:
        return PdfInspectionResult(
            is_valid=False,
            error_message="Uploaded PDF file is empty or too small."
        )

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        return PdfInspectionResult(
            is_valid=False,
            error_message=f"Corrupted or unreadable PDF document: {str(e)}"
        )

    try:
        if doc.is_encrypted:
            return PdfInspectionResult(
                is_encrypted=True,
                is_valid=False,
                error_message="This PDF is encrypted or password-protected. Please upload an unlocked PDF."
            )

        page_count = doc.page_count
        if page_count <= 0:
            return PdfInspectionResult(
                page_count=0,
                is_valid=False,
                error_message="The uploaded PDF contains no pages."
            )

        dims = []
        for i in range(page_count):
            page = doc.load_page(i)
            rect = page.rect
            dims.append((rect.width, rect.height))

        return PdfInspectionResult(
            page_count=page_count,
            is_encrypted=False,
            is_valid=True,
            page_dimensions=dims,
        )
    finally:
        doc.close()


def render_pdf_pages_adaptively(
    pdf_bytes: bytes,
    max_pages: Optional[int] = None,
    target_dpi: int = 200,
    max_pixel_dimension: int = 2500,
) -> List[Image.Image]:
    """
    Renders PDF pages adaptively to PIL Images.
    Adjusts zoom based on page dimensions to balance text sharpness and memory usage.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images: List[Image.Image] = []

    try:
        total_pages = doc.page_count
        pages_to_process = min(total_pages, max_pages) if max_pages else total_pages

        for page_idx in range(pages_to_process):
            page = doc.load_page(page_idx)
            rect = page.rect
            w, h = rect.width, rect.height

            # Standard 72 pt = 1 inch. Target DPI / 72 gives the zoom factor
            base_zoom = target_dpi / 72.0

            # Calculate resulting pixel dimensions
            projected_w = w * base_zoom
            projected_h = h * base_zoom
            max_proj = max(projected_w, projected_h)

            # Adapt zoom if projected size exceeds memory-safe max dimension
            if max_proj > max_pixel_dimension:
                zoom = max_pixel_dimension / max(w, h)
            else:
                zoom = max(1.5, base_zoom)

            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            # Convert pixmap to PIL Image
            img_data = pix.tobytes("png")
            pil_img = Image.open(io.BytesIO(img_data)).convert("RGB")
            images.append(pil_img)

        return images
    finally:
        doc.close()
