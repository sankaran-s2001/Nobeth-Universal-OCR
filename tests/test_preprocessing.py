"""Unit tests for image quality assessment and non-destructive preprocessing."""

import numpy as np
import cv2
from PIL import Image

from utils.image_utils import (
    analyze_image_quality,
    calculate_blur_metric,
    calculate_contrast_metric,
    calculate_resolution_metric,
    create_preprocessed_copy,
    detect_skew_angle,
)
from models.schemas import MetricStatus, ReadinessStatus


def test_blur_metric_sharp_and_blurry():
    # 1. Create a sharp image with high frequency edges (checkerboard)
    sharp_arr = np.zeros((200, 200), dtype=np.uint8)
    sharp_arr[::20, :] = 255
    sharp_arr[:, ::20] = 255
    status_sharp, display_sharp, _, val_sharp = calculate_blur_metric(sharp_arr)
    assert status_sharp in [MetricStatus.GOOD, MetricStatus.ADEQUATE]
    assert val_sharp > 50.0

    # 2. Create a heavily blurred image
    blurry_arr = cv2.GaussianBlur(sharp_arr, (51, 51), 0)
    status_blur, display_blur, _, val_blur = calculate_blur_metric(blurry_arr)
    assert status_blur in [MetricStatus.WARNING, MetricStatus.POOR]
    assert val_blur < val_sharp


def test_contrast_metric_high_and_low():
    # 1. High contrast (black and white)
    high_cont = np.zeros((100, 100), dtype=np.uint8)
    high_cont[:50, :] = 255
    status_high, _, _, val_high = calculate_contrast_metric(high_cont)
    assert status_high == MetricStatus.GOOD
    assert val_high > 50.0

    # 2. Low contrast (flat mid-gray with minimal variation)
    low_cont = np.full((100, 100), 128, dtype=np.uint8)
    low_cont[:10, :] = 130
    status_low, _, _, val_low = calculate_contrast_metric(low_cont)
    assert status_low in [MetricStatus.WARNING, MetricStatus.POOR]
    assert val_low < 20.0


def test_resolution_metric():
    # High resolution
    status_hr, display_hr, _, _ = calculate_resolution_metric(2480, 3508)
    assert status_hr == MetricStatus.GOOD

    # Low resolution
    status_lr, display_lr, _, _ = calculate_resolution_metric(150, 150)
    assert status_lr == MetricStatus.POOR


def test_analyze_image_quality_comprehensive():
    # Create a realistic test document image (white background with black text-like lines)
    img_arr = np.full((800, 600, 3), 255, dtype=np.uint8)
    # Draw simulated text lines
    for y in range(50, 750, 30):
        cv2.line(img_arr, (50, y), (550, y), (0, 0, 0), 2)

    pil_img = Image.fromarray(img_arr)
    report = analyze_image_quality(pil_img)

    assert report.overall_status in [ReadinessStatus.READY, ReadinessStatus.READY_WITH_WARNINGS]
    assert report.readiness_score > 60.0
    assert report.resolution.status in [MetricStatus.GOOD, MetricStatus.ADEQUATE]


def test_non_destructive_preprocessing():
    # Create an image and verify original remains strictly untouched
    original_arr = np.full((500, 500, 3), 200, dtype=np.uint8)
    cv2.putText(original_arr, "SAMPLE TEXT", (50, 250), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    original_img = Image.fromarray(original_arr)

    # Copy pixel snapshot
    original_pixels_before = np.array(original_img).copy()

    processed_img, was_modified = create_preprocessed_copy(original_img, auto_deskew=True, enhance_contrast=True)

    # Verify original pixel buffer was not altered in place
    original_pixels_after = np.array(original_img)
    assert np.array_equal(original_pixels_before, original_pixels_after)
    assert isinstance(processed_img, Image.Image)


def test_detect_skew_angle_and_deskew_correction():
    # 1. Create a synthetic document with horizontal text lines
    img_arr = np.full((400, 600, 3), 255, dtype=np.uint8)
    for y in range(60, 340, 40):
        cv2.line(img_arr, (50, y), (550, y), (0, 0, 0), 3)

    # 2. Known rotation (+5.0 degrees)
    center = (300, 200)
    rot_matrix = cv2.getRotationMatrix2D(center, 5.0, 1.0)
    skewed_arr = cv2.warpAffine(img_arr, rot_matrix, (600, 400), borderValue=(255, 255, 255))
    skewed_pil = Image.fromarray(skewed_arr)

    # Snapshot of original pixels before preprocessing
    skewed_pixels_before = np.array(skewed_pil).copy()

    # 3. Detect skew on rotated image
    gray = cv2.cvtColor(skewed_arr, cv2.COLOR_BGR2GRAY)
    detected_angle = detect_skew_angle(gray)
    assert abs(detected_angle) > 2.0

    # 4. Correct via create_preprocessed_copy
    corrected_pil, was_modified = create_preprocessed_copy(skewed_pil, auto_deskew=True)
    assert was_modified is True
    assert isinstance(corrected_pil, Image.Image)

    # 5. Verify original image was not modified in place
    assert np.array_equal(skewed_pixels_before, np.array(skewed_pil))

    # Corrected image should have angle within small tolerance (<= 1.0 degree)
    corrected_gray = cv2.cvtColor(np.array(corrected_pil), cv2.COLOR_RGB2GRAY)
    final_angle = detect_skew_angle(corrected_gray)
    assert abs(final_angle) <= 1.0

    # 6. Already aligned image is not unnecessarily rotated
    aligned_pil = Image.fromarray(img_arr)
    aligned_copy, aligned_mod = create_preprocessed_copy(aligned_pil, auto_deskew=True, enhance_contrast=False)
    assert aligned_mod is False

    # 7. Blank or unsuitable images are handled safely
    blank_pil = Image.new("RGB", (300, 300), color="white")
    blank_copy, blank_mod = create_preprocessed_copy(blank_pil, auto_deskew=True)
    assert isinstance(blank_copy, Image.Image)
