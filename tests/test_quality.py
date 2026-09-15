"""Unit tests for Image Quality Assessment (app/quality.py)."""
import cv2
import numpy as np

from app.quality import check_blur, check_exposure, check_glare, assess_image_quality
from app.constants import DEMO_SAMPLES_DIR


def _sharp():
    img = np.zeros((300, 400), dtype=np.uint8)
    img[::20, :] = 255
    img[:, ::20] = 255
    return img


def test_sharp_image_passes_blur():
    passed, score = check_blur(_sharp())
    assert passed
    assert score > 75.0


def test_blurred_image_fails_blur():
    blurred = cv2.GaussianBlur(_sharp(), (31, 31), 10.0)
    passed, score = check_blur(blurred)
    assert not passed
    assert score < 75.0


def test_underexposed_image_fails_exposure():
    dark = np.full((200, 200), 10, dtype=np.uint8)
    passed, status, _u, _o = check_exposure(dark)
    assert not passed
    assert status == "underexposed"


def test_overexposed_image_fails_exposure():
    bright = np.full((200, 200), 250, dtype=np.uint8)
    passed, status, _u, _o = check_exposure(bright)
    assert not passed
    assert status == "overexposed"


def test_glare_detection():
    bgr = np.full((200, 200, 3), (120, 120, 120), dtype=np.uint8)
    cv2.circle(bgr, (100, 100), 40, (255, 255, 255), -1)
    passed, detected, _ratio = check_glare(bgr)
    assert detected
    assert not passed


def test_full_quality_rejection_on_blurry_sample():
    path = DEMO_SAMPLES_DIR / "sample_blurry_rejection.jpg"
    img = cv2.imread(str(path))
    report = assess_image_quality(img, card_detected=True)
    assert not report.passed
    assert "blurry" in " ".join(report.issues).lower()
