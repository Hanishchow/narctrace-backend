"""Unit tests for Kit Profile loading + Classification Engine (app/engine.py)."""
from app.engine import list_available_profiles, get_kit_profile, classify_result
from app.models import ColorMetrics


def _metrics(lab, dpos, dneg):
    return ColorMetrics(raw_rgb=[0, 0, 0], calibrated_rgb=[0, 0, 0], calibrated_lab=lab,
                        delta_e_positive=dpos, delta_e_negative=dneg)


def test_profiles_loaded_and_marked_simulated():
    profiles = list_available_profiles()
    alpha = get_kit_profile("SIM-PROFILE-ALPHA")
    beta = get_kit_profile("SIM-PROFILE-BETA")
    assert len(profiles) >= 2
    assert alpha is not None and beta is not None
    assert alpha.is_simulated and beta.is_simulated
    assert "SIMULATED" in alpha.disclaimer


def test_classify_positive_result():
    alpha = get_kit_profile("SIM-PROFILE-ALPHA")
    outcome, reason = classify_result(_metrics([27.0, 41.0, -36.0], 1.2, 42.0), alpha)
    assert outcome == "Positive"
    assert "matches positive proxy target" in reason


def test_classify_negative_result():
    alpha = get_kit_profile("SIM-PROFILE-ALPHA")
    outcome, reason = classify_result(_metrics([80.0, -2.0, 34.0], 45.0, 1.5), alpha)
    assert outcome == "Negative"
    assert "matches negative proxy target" in reason


def test_classify_inconclusive_when_out_of_bounds():
    alpha = get_kit_profile("SIM-PROFILE-ALPHA")
    outcome, reason = classify_result(_metrics([87.0, -86.0, 83.0], 55.0, 48.0), alpha)
    assert outcome == "Inconclusive"
    assert "outside all expected profile boundaries" in reason


def test_classify_inconclusive_when_ambiguous_margin():
    alpha = get_kit_profile("SIM-PROFILE-ALPHA")
    outcome, reason = classify_result(_metrics([55.0, 5.0, -5.0], 11.0, 12.5), alpha)
    assert outcome == "Inconclusive"
    assert "Ambiguous reaction" in reason
