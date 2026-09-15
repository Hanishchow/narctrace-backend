"""
Deterministic Colour Analysis (ported from Technocrats reference `src/color.py`).
Standard sRGB -> CIELAB (D65) conversion and CIEDE2000 Delta E. No ML.
"""
import numpy as np
from typing import Tuple, List
from skimage.color import rgb2lab, deltaE_ciede2000
from app.models import ColorMetrics


def rgb_to_cielab(rgb: Tuple[int, int, int]) -> List[float]:
    """Converts sRGB (0-255) to CIELAB (L*, a*, b*) under standard D65 illuminant."""
    r, g, b = rgb
    rgb_norm = np.array([[[r / 255.0, g / 255.0, b / 255.0]]], dtype=np.float64)
    lab = rgb2lab(rgb_norm)[0, 0]
    return [float(lab[0]), float(lab[1]), float(lab[2])]


def calculate_delta_e00(lab1: List[float], lab2: List[float]) -> float:
    """
    Colour difference via CIEDE2000 (Delta E 00). Used as a standard colour-difference
    metric for demonstration only; NOT validated for real drug kits.
    """
    arr1 = np.array(lab1, dtype=np.float64)
    arr2 = np.array(lab2, dtype=np.float64)
    diff = float(deltaE_ciede2000(arr1, arr2))
    return max(0.0, diff)


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Formats an (R, G, B) 0-255 tuple as a #rrggbb hex string."""
    r, g, b = (int(max(0, min(255, round(c)))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def compute_color_metrics(
    raw_rgb: Tuple[int, int, int],
    calibrated_rgb: Tuple[int, int, int],
    target_pos_lab: List[float],
    target_neg_lab: List[float],
) -> ColorMetrics:
    """Computes CIELAB coords and Delta E distances to positive/negative profile targets."""
    calibrated_lab = rgb_to_cielab(calibrated_rgb)
    dE_pos = calculate_delta_e00(calibrated_lab, target_pos_lab)
    dE_neg = calculate_delta_e00(calibrated_lab, target_neg_lab)
    return ColorMetrics(
        raw_rgb=[int(c) for c in raw_rgb],
        calibrated_rgb=[int(c) for c in calibrated_rgb],
        calibrated_lab=calibrated_lab,
        delta_e_positive=dE_pos,
        delta_e_negative=dE_neg,
    )
