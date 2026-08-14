"""Image loading, quality metrics analysis, and non-destructive preprocessing utilities."""

import io
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import Image, ImageOps

# Register HEIF opener if pillow_heif is available
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

from models.schemas import (
    MetricStatus,
    ReadinessMetric,
    ReadinessReport,
    ReadinessStatus,
)


def load_image_safely(image_bytes: bytes) -> Image.Image:
    """
    Loads PIL Image from bytes safely with EXIF orientation normalization.
    Raises ValueError if image cannot be parsed.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        # Handle EXIF orientation if present
        try:
            image = ImageOps.exif_transpose(image)
        except Exception:
            pass

        # Convert to RGB mode (handles RGBA, Palette, CMYK, etc.)
        if image.mode != "RGB":
            image = image.convert("RGB")
        return image
    except Exception as e:
        raise ValueError(f"Failed to decode image: {str(e)}")


def pil_to_opencv(image: Image.Image) -> np.ndarray:
    """Converts a PIL Image (RGB) to an OpenCV BGR numpy array."""
    np_img = np.array(image)
    return cv2.cvtColor(np_img, cv2.COLOR_RGB2BGR)


def opencv_to_pil(cv_img: np.ndarray) -> Image.Image:
    """Converts an OpenCV BGR numpy array to a PIL Image (RGB)."""
    rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb_img)


def calculate_blur_metric(gray_img: np.ndarray) -> Tuple[MetricStatus, str, str, float]:
    """
    Computes blur using the variance of the Laplacian.
    Returns: (status, display_val, details, raw_val)
    """
    laplacian_var = float(cv2.Laplacian(gray_img, cv2.CV_64F).var())

    if laplacian_var >= 250.0:
        return MetricStatus.GOOD, "Sharp (Low Blur)", f"Laplacian variance: {laplacian_var:.1f}", laplacian_var
    elif laplacian_var >= 80.0:
        return MetricStatus.ADEQUATE, "Moderate Sharpness", f"Laplacian variance: {laplacian_var:.1f}", laplacian_var
    elif laplacian_var >= 30.0:
        return MetricStatus.WARNING, "Slightly Blurry", f"Laplacian variance: {laplacian_var:.1f} (minor blur detected)", laplacian_var
    else:
        return MetricStatus.POOR, "High Blur", f"Laplacian variance: {laplacian_var:.1f} (document may be difficult to read)", laplacian_var


def calculate_contrast_metric(gray_img: np.ndarray) -> Tuple[MetricStatus, str, str, float]:
    """
    Computes RMS contrast: standard deviation of pixel intensities.
    Returns: (status, display_val, details, raw_val)
    """
    rms_contrast = float(np.std(gray_img))

    if rms_contrast >= 55.0:
        return MetricStatus.GOOD, "Good Contrast", f"RMS contrast: {rms_contrast:.1f}", rms_contrast
    elif rms_contrast >= 35.0:
        return MetricStatus.ADEQUATE, "Adequate Contrast", f"RMS contrast: {rms_contrast:.1f}", rms_contrast
    elif rms_contrast >= 20.0:
        return MetricStatus.WARNING, "Low Contrast", f"RMS contrast: {rms_contrast:.1f} (faint or faded text)", rms_contrast
    else:
        return MetricStatus.POOR, "Poor Contrast", f"RMS contrast: {rms_contrast:.1f} (text may blend into background)", rms_contrast


def calculate_brightness_metric(gray_img: np.ndarray) -> Tuple[MetricStatus, str, str, float]:
    """
    Computes mean luminance (0-255).
    Returns: (status, display_val, details, raw_val)
    """
    mean_bright = float(np.mean(gray_img))

    if 70.0 <= mean_bright <= 230.0:
        return MetricStatus.GOOD, "Balanced", f"Mean brightness: {mean_bright:.1f}/255", mean_bright
    elif (45.0 <= mean_bright < 70.0) or (230.0 < mean_bright <= 245.0):
        return MetricStatus.ADEQUATE, "Acceptable", f"Mean brightness: {mean_bright:.1f}/255", mean_bright
    elif mean_bright < 45.0:
        return MetricStatus.WARNING, "Under-exposed (Dark)", f"Mean brightness: {mean_bright:.1f}/255 (shadowed or dark)", mean_bright
    else:
        return MetricStatus.WARNING, "Over-exposed (Bright)", f"Mean brightness: {mean_bright:.1f}/255 (washed out)", mean_bright


def detect_skew_angle(gray_img: np.ndarray) -> float:
    """
    Detects skew angle in degrees using thresholding and minAreaRect on contours.
    Angle is bounded in [-45, 45] degrees.
    """
    try:
        # Invert and threshold
        blur = cv2.GaussianBlur(gray_img, (5, 5), 0)
        _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Morphological dilation to connect text lines
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3))
        dilated = cv2.dilate(thresh, kernel, iterations=2)

        contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        angles = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < 500:
                continue
            rect = cv2.minAreaRect(c)
            angle = rect[-1]
            if angle < -45:
                angle = 90 + angle
            elif angle > 45:
                angle = angle - 90
            angles.append(angle)

        if angles:
            median_angle = float(np.median(angles))
            if abs(median_angle) <= 45.0:
                return round(median_angle, 2)
    except Exception:
        pass
    return 0.0


def calculate_resolution_metric(width: int, height: int) -> Tuple[MetricStatus, str, str, float]:
    """
    Evaluates image resolution based on dimensions and megapixel count.
    """
    mp = (width * height) / 1_000_000.0
    dim_str = f"{width} × {height} ({mp:.1f} MP)"

    min_dim = min(width, height)
    if min_dim >= 1000 and mp >= 1.0:
        return MetricStatus.GOOD, "High Resolution", dim_str, mp
    elif min_dim >= 600 and mp >= 0.4:
        return MetricStatus.ADEQUATE, "Adequate Resolution", dim_str, mp
    elif min_dim >= 300:
        return MetricStatus.WARNING, "Low Resolution", f"{dim_str} (small text may be degraded)", mp
    else:
        return MetricStatus.POOR, "Very Low Resolution", f"{dim_str} (text may be unreadable)", mp


def analyze_image_quality(image: Image.Image) -> ReadinessReport:
    """
    Analyzes visual quality and returns a complete, honest ReadinessReport.
    """
    width, height = image.size
    cv_img = pil_to_opencv(image)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

    # 1. Resolution
    res_status, res_display, res_details, res_val = calculate_resolution_metric(width, height)

    # 2. Blur
    blur_status, blur_display, blur_details, blur_val = calculate_blur_metric(gray)

    # 3. Contrast
    cont_status, cont_display, cont_details, cont_val = calculate_contrast_metric(gray)

    # 4. Brightness
    bright_status, bright_display, bright_details, bright_val = calculate_brightness_metric(gray)

    # 5. Skew
    skew_angle = detect_skew_angle(gray)
    if abs(skew_angle) <= 0.8:
        skew_status = MetricStatus.GOOD
        skew_display = "Aligned"
        skew_details = f"Skew angle: {skew_angle:+.1f}°"
    elif abs(skew_angle) <= 3.0:
        skew_status = MetricStatus.ADEQUATE
        skew_display = f"Slight Skew ({skew_angle:+.1f}°)"
        skew_details = f"Auto-deskew available ({skew_angle:+.1f}°)"
    elif abs(skew_angle) <= 15.0:
        skew_status = MetricStatus.WARNING
        skew_display = f"Noticeable Skew ({skew_angle:+.1f}°)"
        skew_details = f"Significant rotation detected ({skew_angle:+.1f}°)"
    else:
        skew_status = MetricStatus.POOR
        skew_display = f"Severe Skew ({skew_angle:+.1f}°)"
        skew_details = f"Large rotation detected ({skew_angle:+.1f}°)"

    # Warnings collection
    warnings = []
    if blur_status in [MetricStatus.WARNING, MetricStatus.POOR]:
        warnings.append(f"Image has high blur ({blur_display}).")
    if cont_status in [MetricStatus.WARNING, MetricStatus.POOR]:
        warnings.append(f"Image has low contrast ({cont_display}).")
    if bright_status == MetricStatus.WARNING:
        warnings.append(f"Image exposure is suboptimal ({bright_display}).")
    if res_status in [MetricStatus.WARNING, MetricStatus.POOR]:
        warnings.append(f"Image resolution is low ({res_display}).")
    if abs(skew_angle) > 3.0:
        warnings.append(f"Document has noticeable skew ({skew_angle:+.1f}°).")

    # Readability computation based on combined metric health
    status_weights = {
        MetricStatus.GOOD: 1.0,
        MetricStatus.ADEQUATE: 0.85,
        MetricStatus.WARNING: 0.55,
        MetricStatus.POOR: 0.25,
        MetricStatus.UNCERTAIN: 0.5,
    }

    score = (
        0.30 * status_weights[blur_status] +
        0.25 * status_weights[cont_status] +
        0.20 * status_weights[res_status] +
        0.15 * status_weights[bright_status] +
        0.10 * status_weights[skew_status]
    ) * 100.0

    readiness_score = round(score, 1)

    if readiness_score >= 82.0 and not any(s == MetricStatus.POOR for s in [blur_status, cont_status, res_status]):
        overall_status = ReadinessStatus.READY
        readability_status = MetricStatus.GOOD
        readability_display = "Clear & High Quality"
    elif readiness_score >= 50.0:
        overall_status = ReadinessStatus.READY_WITH_WARNINGS
        readability_status = MetricStatus.ADEQUATE if readiness_score >= 68.0 else MetricStatus.WARNING
        readability_display = "Readable (Moderate Warnings)"
    else:
        overall_status = ReadinessStatus.LOW_QUALITY
        readability_status = MetricStatus.POOR
        readability_display = "Challenging / Low Quality"

    readability_details = f"Quality score: {readiness_score:.1f}%. Extraction will proceed."

    return ReadinessReport(
        overall_status=overall_status,
        readiness_score=readiness_score,
        resolution=ReadinessMetric(name="Resolution", status=res_status, value_display=res_display, details=res_details),
        blur=ReadinessMetric(name="Blur", status=blur_status, value_display=blur_display, details=blur_details),
        contrast=ReadinessMetric(name="Contrast", status=cont_status, value_display=cont_display, details=cont_details),
        brightness=ReadinessMetric(name="Brightness", status=bright_status, value_display=bright_display, details=bright_details),
        skew=ReadinessMetric(name="Orientation / Skew", status=skew_status, value_display=skew_display, details=skew_details),
        readability=ReadinessMetric(name="Readability", status=readability_status, value_display=readability_display, details=readability_details),
        warnings=warnings,
    )


def create_preprocessed_copy(image: Image.Image, auto_deskew: bool = True, enhance_contrast: bool = True) -> Tuple[Image.Image, bool]:
    """
    Creates a non-destructive preprocessed copy of the image for Gemini Vision.
    Leaves the original image untouched.
    Returns: (preprocessed_image, was_modified)
    """
    modified = False
    cv_img = pil_to_opencv(image)
    h, w = cv_img.shape[:2]

    # 1. Safe Deskew if significant skew detected
    if auto_deskew:
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        skew_angle = detect_skew_angle(gray)
        if 0.8 < abs(skew_angle) <= 25.0:
            center = (w // 2, h // 2)
            rot_mat = cv2.getRotationMatrix2D(center, skew_angle, 1.0)
            cv_img = cv2.warpAffine(
                cv_img, rot_mat, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE
            )
            modified = True

    # 2. Subtle Adaptive Contrast Enhancement (CLAHE) if contrast is low
    if enhance_contrast:
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        rms = float(np.std(gray))
        if rms < 35.0:
            # Low contrast - apply gentle CLAHE to luminance channel
            lab = cv2.cvtColor(cv_img, cv2.COLOR_BGR2LAB)
            l_chan, a_chan, b_chan = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            cl = clahe.apply(l_chan)
            limg = cv2.merge((cl, a_chan, b_chan))
            cv_img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
            modified = True

    # 3. Safe downsampling if image exceeds 3072px on longest side
    max_dim = max(h, w)
    if max_dim > 3072:
        scale = 3072.0 / max_dim
        new_w, new_h = int(w * scale), int(h * scale)
        cv_img = cv2.resize(cv_img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        modified = True

    if modified:
        return opencv_to_pil(cv_img), True
    return image.copy(), False
