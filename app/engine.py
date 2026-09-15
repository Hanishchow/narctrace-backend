"""
Configurable Multi-Kit Interpretation Engine (ported from Technocrats reference
`src/engine.py`). Evaluates calibrated CIELAB colours and Delta E distances to produce
Positive / Negative / Inconclusive. Inconclusive is a first-class result.
"""
import json
from pathlib import Path
from typing import List, Optional, Tuple
from app.constants import PROFILES_DIR
from app.models import KitProfile, ColorMetrics


def load_profile_from_file(filepath: Path) -> KitProfile:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return KitProfile.from_dict(data)


def list_available_profiles() -> List[KitProfile]:
    profiles = []
    for p in sorted(PROFILES_DIR.glob("*.json")):
        try:
            profiles.append(load_profile_from_file(p))
        except Exception as e:  # pragma: no cover
            print(f"Warning: Failed to load profile {p}: {e}")
    return profiles


def get_kit_profile(profile_id: str) -> Optional[KitProfile]:
    for profile in list_available_profiles():
        if profile.profile_id.lower() == profile_id.lower():
            return profile
    return None


def classify_result(metrics: ColorMetrics, profile: KitProfile) -> Tuple[str, str]:
    """
    Deterministic rule engine over CIEDE2000 Delta E distances to kit-profile targets.
    Returns (outcome, reasoning). Inconclusive covers: out-of-bounds ΔE, ambiguity within
    margin, or failure to decisively satisfy positive/negative rules.
    """
    dE_pos = metrics.delta_e_positive
    dE_neg = metrics.delta_e_negative
    max_pos = profile.positive_target.max_delta_e
    max_neg = profile.negative_target.max_delta_e
    margin = profile.ambiguity_margin
    max_acceptable = profile.max_acceptable_delta_e

    # Condition 1: Exceeds all acceptable reaction limits
    if dE_pos > max_acceptable and dE_neg > max_acceptable:
        return (
            "Inconclusive",
            f"Reaction colour is outside all expected profile boundaries "
            f"(dE_pos={dE_pos:.1f}, dE_neg={dE_neg:.1f} > {max_acceptable:.1f}).",
        )

    # Condition 2: Ambiguous boundary between positive and negative
    diff = abs(dE_pos - dE_neg)
    if diff < margin and (dE_pos <= max_pos or dE_neg <= max_neg):
        return (
            "Inconclusive",
            f"Ambiguous reaction: separation between positive and negative targets "
            f"({diff:.1f}) is within ambiguity margin ({margin:.1f}).",
        )

    # Condition 3: Positive
    if dE_pos <= max_pos and (dE_neg - dE_pos) >= margin:
        return (
            "Positive",
            f"Calibrated colour matches positive proxy target "
            f"(dE={dE_pos:.1f} <= {max_pos:.1f}, margin={dE_neg - dE_pos:.1f}).",
        )

    # Condition 4: Negative
    if dE_neg <= max_neg and (dE_pos - dE_neg) >= margin:
        return (
            "Negative",
            f"Calibrated colour matches negative proxy target "
            f"(dE={dE_neg:.1f} <= {max_neg:.1f}, margin={dE_pos - dE_neg:.1f}).",
        )

    # Fallthrough
    return (
        "Inconclusive",
        f"Reaction does not meet decisive criteria for positive or negative rules "
        f"(dE_pos={dE_pos:.1f}, dE_neg={dE_neg:.1f}).",
    )
