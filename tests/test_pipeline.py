"""End-to-end pipeline tests across the synthetic demo samples (app/pipeline.py)."""
import pytest

from app.constants import DEMO_SAMPLES_DIR
from app.engine import get_kit_profile
from app.pipeline import run_pipeline


def _run(sample, profile_id):
    data = (DEMO_SAMPLES_DIR / sample).read_bytes()
    return run_pipeline(data, get_kit_profile(profile_id))


@pytest.mark.parametrize("sample,profile_id,expected", [
    ("sample_alpha_positive.jpg", "SIM-PROFILE-ALPHA", "Positive"),
    ("sample_alpha_negative.jpg", "SIM-PROFILE-ALPHA", "Negative"),
    ("sample_alpha_inconclusive.jpg", "SIM-PROFILE-ALPHA", "Inconclusive"),
    ("sample_beta_positive.jpg", "SIM-PROFILE-BETA", "Positive"),
    ("sample_beta_negative.jpg", "SIM-PROFILE-BETA", "Negative"),
])
def test_classification_samples(sample, profile_id, expected):
    res = _run(sample, profile_id)
    assert res.success
    assert res.quality_report.passed
    assert res.result == expected


def test_blurry_rejection():
    res = _run("sample_blurry_rejection.jpg", "SIM-PROFILE-ALPHA")
    assert not res.success
    assert not res.quality_report.blur_passed
    assert res.result is None


def test_glare_rejection():
    res = _run("sample_glare_rejection.jpg", "SIM-PROFILE-ALPHA")
    assert not res.success
    assert res.quality_report.glare_detected
    assert res.result is None
