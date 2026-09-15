"""
MVP-Simple Colour Calibration (ported from Technocrats reference `src/calibration.py`).
Linear per-channel white-point gain adjustment from the observed reference-card white patch.
"""
import numpy as np
from typing import Tuple
from app.constants import PROTOTYPE_CARD_NOMINAL
from app.models import CalibrationResult


def compute_calibration_gains(
    observed_white_rgb: Tuple[float, float, float],
    nominal_white_rgb: Tuple[float, float, float] = PROTOTYPE_CARD_NOMINAL["white"],
) -> Tuple[float, float, float]:
    """
    Per-channel gain multipliers: k_c = nominal_white_c / max(observed_white_c, 1.0).
    Clamped to [0.3, 3.0] to prevent extreme distortion.
    """
    gains = []
    for obs, nom in zip(observed_white_rgb, nominal_white_rgb):
        obs_safe = max(float(obs), 1.0)
        gain = nom / obs_safe
        gain_clamped = max(0.3, min(3.0, gain))
        gains.append(gain_clamped)
    return (float(gains[0]), float(gains[1]), float(gains[2]))


def apply_color_calibration(
    observed_reaction_rgb: Tuple[float, float, float],
    observed_white_rgb: Tuple[float, float, float],
) -> Tuple[Tuple[int, int, int], CalibrationResult]:
    """Calibrates the reaction-zone RGB using detected white-patch gains."""
    k_r, k_g, k_b = compute_calibration_gains(observed_white_rgb)

    r_cal = int(np.clip(round(observed_reaction_rgb[0] * k_r), 0, 255))
    g_cal = int(np.clip(round(observed_reaction_rgb[1] * k_g), 0, 255))
    b_cal = int(np.clip(round(observed_reaction_rgb[2] * k_b), 0, 255))
    calibrated_rgb = (r_cal, g_cal, b_cal)

    result = CalibrationResult(
        observed_white_rgb=[round(x, 1) for x in observed_white_rgb],
        gains=[round(k_r, 4), round(k_g, 4), round(k_b, 4)],
        success=True,
        message=f"Illumination normalized: R x{k_r:.3f}, G x{k_g:.3f}, B x{k_b:.3f}",
    )
    return calibrated_rgb, result
