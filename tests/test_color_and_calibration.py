"""Unit tests for Calibration + deterministic Colour Science (app/calibration.py, app/color.py)."""
import pytest

from app.calibration import compute_calibration_gains, apply_color_calibration
from app.color import rgb_to_cielab, calculate_delta_e00, rgb_to_hex


def test_calibration_gain_computation():
    kr, kg, kb = compute_calibration_gains((250.0, 220.0, 180.0), nominal_white_rgb=(240.0, 240.0, 240.0))
    assert kr == pytest.approx(240.0 / 250.0, abs=1e-3)
    assert kb == pytest.approx(240.0 / 180.0, abs=1e-3)


def test_apply_color_calibration_boosts_blue():
    calibrated_rgb, res = apply_color_calibration((100.0, 100.0, 80.0), (240.0, 240.0, 120.0))
    assert res.success
    assert calibrated_rgb[2] > 80.0


def test_rgb_to_cielab_bounds():
    assert rgb_to_cielab((255, 255, 255))[0] == pytest.approx(100.0, abs=1.0)
    assert rgb_to_cielab((0, 0, 0))[0] == pytest.approx(0.0, abs=1.0)


def test_delta_e_identical_colors():
    lab = [50.0, 20.0, -10.0]
    assert calculate_delta_e00(lab, lab) == pytest.approx(0.0, abs=0.01)


def test_delta_e_distinct_colors():
    assert calculate_delta_e00([53.2, 80.1, 67.2], [87.7, -86.2, 83.2]) > 50.0


def test_rgb_to_hex():
    assert rgb_to_hex((91, 45, 145)) == "#5b2d91"
    assert rgb_to_hex((0, 0, 0)) == "#000000"
    assert rgb_to_hex((255, 255, 255)) == "#ffffff"
