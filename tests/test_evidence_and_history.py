"""
Tests for SHA-256 evidence hashing, FT-##### ids, record assembly, and LocalStore
persistence/search (app/evidence.py, app/store/local.py).
"""
import hashlib

from app.evidence import (
    compute_image_sha256, verify_image_integrity, format_test_id, build_evidence_record,
)
from app.engine import get_kit_profile
from app.models import QualityReport, ColorMetrics

SAMPLE = b"SIMULATED_TEST_IMAGE_BYTES_123456"
EXPECTED = hashlib.sha256(SAMPLE).hexdigest()

QUALITY = QualityReport(
    passed=True, blur_score=150.0, blur_passed=True, exposure_status="normal",
    exposure_passed=True, glare_detected=False, glare_passed=True, card_visible=True, issues=[],
)
METRICS = ColorMetrics(
    raw_rgb=[95, 35, 120], calibrated_rgb=[95, 35, 120], calibrated_lab=[27.0, 41.0, -36.0],
    delta_e_positive=1.2, delta_e_negative=42.0,
)


def test_sha256_computation_and_integrity():
    assert compute_image_sha256(SAMPLE) == EXPECTED
    assert verify_image_integrity(SAMPLE, EXPECTED)
    assert not verify_image_integrity(b"tampered", EXPECTED)


def test_test_id_format():
    assert format_test_id(42) == "FT-00042"
    assert format_test_id(1) == "FT-00001"


def test_build_evidence_record_shape():
    rec = build_evidence_record(
        test_id="FT-00001", image_bytes=SAMPLE, result="Positive",
        profile=get_kit_profile("SIM-PROFILE-ALPHA"), quality=QUALITY, color_metrics=METRICS,
        image_path="FT-00001.jpg", operator_id="OFFICER-99",
        gps={"lat": 28.61, "lon": 77.20, "label": "Delhi"},
    )
    assert rec.test_id == "FT-00001"
    assert rec.image_sha256 == EXPECTED
    assert rec.operator_id == "OFFICER-99"
    assert rec.color["hex"].startswith("#")
    assert rec.gps == {"lat": 28.61, "lon": 77.20, "label": "Delhi"}
    assert rec.quality["glare"] is False


def test_local_store_persist_and_search(local_store):
    tid = local_store.next_test_id()
    assert tid == "FT-00001"
    path = local_store.save_evidence_image(tid, SAMPLE)
    rec = build_evidence_record(
        test_id=tid, image_bytes=SAMPLE, result="Positive",
        profile=get_kit_profile("SIM-PROFILE-ALPHA"), quality=QUALITY, color_metrics=METRICS,
        image_path=path, operator_id="OFFICER-TEST-99", gps=None,
    )
    local_store.save_record(rec)

    got = local_store.get_record(tid)
    assert got is not None and got["result"] == "Positive"
    assert got["image_sha256"] == EXPECTED

    assert len(local_store.search_records(query="OFFICER-TEST-99")) == 1
    assert any(r["test_id"] == tid for r in local_store.search_records(result_filter="Positive"))

    # next id increments after a save
    assert local_store.next_test_id() == "FT-00002"

    # evidence bytes round-trip
    found = local_store.read_evidence_bytes(path)
    assert found is not None and found[0] == SAMPLE


def test_local_store_auth_stub(local_store):
    auth = local_store.authenticate("BADGE-7", "pw")
    assert auth.token and auth.officer["badge_id"] == "BADGE-7"
