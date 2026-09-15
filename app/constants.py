"""
Deterministic colour-science constants and data paths (ported faithfully from the
Technocrats-SIH26231 reference `src/config.py`).

NOTE: Every threshold and reference-card value here is explicitly SIMULATED / PROXY
for safe demonstration. This module contains NO real narcotic test data.
"""
from pathlib import Path

# --- Base paths (repo-relative, independent of secrets/env) ---
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROFILES_DIR = DATA_DIR / "profiles"
DEMO_SAMPLES_DIR = DATA_DIR / "demo_samples"
EVIDENCE_DIR = DATA_DIR / "evidence"

for _d in (DATA_DIR, PROFILES_DIR, DEMO_SAMPLES_DIR, EVIDENCE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- Image quality thresholds (unchanged science) ---
MIN_LAPLACIAN_VARIANCE = 50.0       # Below this = blur (at standard 640px width)
STANDARD_BLUR_WIDTH = 640           # Standardized evaluation width (deterministic)
MAX_UNDEREXPOSED_RATIO = 0.45       # >45% dark pixels (<20) = underexposed
MAX_OVEREXPOSED_RATIO = 0.25        # >25% clipped pixels (>245) = overexposed
MAX_GLARE_RATIO = 0.08              # >8% specular hotspot in reaction zone = glare

# --- Prototype reference card nominal values (SIMULATED, not a field-kit standard) ---
PROTOTYPE_CARD_NOMINAL = {
    "white": (240, 240, 240),
    "gray": (128, 128, 128),
    "black": (25, 25, 25),
    "reference_blue": (40, 80, 200),
}

# --- Standard presumptive-only disclaimer ---
STANDARD_DISCLAIMER = (
    "PRESUMPTIVE FIELD-TEST RESULT ONLY. "
    "Does not replace laboratory confirmatory testing. "
    "This system uses simulated kit profiles and safe proxy reactions for demonstration purposes."
)
