"""
API route tests via FastAPI TestClient (STORE_BACKEND=local, no network).
Uses an isolated LocalStore via dependency override so the repo DB isn't polluted.
"""
import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.deps import store_dep
from app.constants import DEMO_SAMPLES_DIR
from app.store.local import LocalStore


@pytest.fixture()
def client(tmp_path):
    store = LocalStore(db_path=tmp_path / "api.db", evidence_dir=tmp_path / "evidence")
    app.dependency_overrides[store_dep] = lambda: store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth(client):
    r = client.post("/api/auth/login", json={"badge_id": "OP-1", "password": "pw"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_login_shape(client):
    r = client.post("/api/auth/login", json={"badge_id": "OP-1", "password": "pw"})
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    assert body["officer"]["badge_id"] == "OP-1"


def test_profiles(client):
    r = client.get("/api/profiles")
    assert r.status_code == 200
    body = r.json()
    assert body["success"]
    assert len(body["profiles"]) >= 2


def test_analyze_requires_bearer(client):
    r = client.post("/api/analyze", files={"image": ("x.jpg", b"x", "image/jpeg")},
                    data={"profile_id": "SIM-PROFILE-ALPHA"})
    assert r.status_code == 401


def test_analyze_rejects_fabricated_bearer(client):
    r = client.post(
        "/api/analyze",
        headers={"Authorization": "Bearer fabricated"},
        files={"image": ("x.jpg", b"x", "image/jpeg")},
        data={"profile_id": "SIM-PROFILE-ALPHA"},
    )
    assert r.status_code == 401


def test_analyze_positive_flow(client):
    headers = _auth(client)
    img = (DEMO_SAMPLES_DIR / "sample_alpha_positive.jpg").read_bytes()
    r = client.post(
        "/api/analyze",
        headers=headers,
        files={"image": ("sample.jpg", io.BytesIO(img), "image/jpeg")},
        data={
            "profile_id": "SIM-PROFILE-ALPHA",
            "operator_id": "WEB-TESTER",
            "gps": '{"lat": 28.61, "lon": 77.20, "label": "Delhi"}',
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"]
    assert body["result"] == "Positive"
    assert body["test_id"].startswith("FT-")
    assert body["quality"]["passed"]
    assert body["color"]["hex"].startswith("#")
    assert body["evidence"]["operator_id"] == "OP-1"
    assert body["evidence"]["gps"]["label"] == "Delhi"
    assert body["evidence"]["image_sha256"]
    assert "PRESUMPTIVE" in body["disclaimer"]

    # history round-trip
    tid = body["test_id"]
    h = client.get("/api/history", headers=headers)
    assert h.status_code == 200
    assert h.json()["count"] >= 1

    one = client.get(f"/api/history/{tid}", headers=headers)
    assert one.status_code == 200
    assert one.json()["record"]["test_id"] == tid

    # evidence bytes
    ev = client.get(f"/api/evidence/{tid}.jpg", headers=headers)
    assert ev.status_code == 200
    assert ev.content == img

    verification = client.get(f"/api/history/{tid}/verify", headers=headers)
    assert verification.status_code == 200
    assert verification.json()["valid"] is True


def test_analyze_blurry_returns_422(client):
    headers = _auth(client)
    img = (DEMO_SAMPLES_DIR / "sample_blurry_rejection.jpg").read_bytes()
    r = client.post(
        "/api/analyze",
        headers=headers,
        files={"image": ("blurry.jpg", io.BytesIO(img), "image/jpeg")},
        data={"profile_id": "SIM-PROFILE-ALPHA"},
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["success"] is False
    assert detail["quality"]["passed"] is False


def test_capture_preview_does_not_persist_record(client):
    headers = _auth(client)
    img = (DEMO_SAMPLES_DIR / "sample_alpha_positive.jpg").read_bytes()
    response = client.post(
        "/api/capture-preview",
        headers=headers,
        files={"image": ("sample.jpg", io.BytesIO(img), "image/jpeg")},
        data={"profile_id": "SIM-PROFILE-ALPHA"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert client.get("/api/history", headers=headers).json()["count"] == 0


def test_idempotent_capture_returns_original_receipt(client):
    headers = {**_auth(client), "Idempotency-Key": "capture-unique-001"}
    img = (DEMO_SAMPLES_DIR / "sample_alpha_positive.jpg").read_bytes()
    first = client.post(
        "/api/analyze", headers=headers,
        files={"image": ("sample.jpg", io.BytesIO(img), "image/jpeg")},
        data={"profile_id": "SIM-PROFILE-ALPHA"},
    )
    second = client.post(
        "/api/analyze", headers=headers,
        files={"image": ("sample.jpg", io.BytesIO(img), "image/jpeg")},
        data={"profile_id": "SIM-PROFILE-ALPHA"},
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["test_id"] == second.json()["test_id"]
    assert client.get("/api/history", headers=headers).json()["count"] == 1


def test_history_requires_bearer(client):
    assert client.get("/api/history").status_code == 401


def test_evidence_missing_404(client):
    headers = _auth(client)
    assert client.get("/api/evidence/nope.jpg", headers=headers).status_code == 404


def test_case_timeline_enforces_versions_and_owner(client):
    headers = _auth(client)
    created = client.post("/api/v2/cases", headers=headers, json={"reference": "CASE-24", "title": "Synthetic field sample"})
    assert created.status_code == 200
    case = created.json()["case"]
    assert case["status"] == "open"
    submitted = client.post(
        f"/api/v2/cases/{case['case_id']}/events",
        headers=headers,
        json={"action": "submit", "expected_version": 1},
    )
    assert submitted.status_code == 200
    assert submitted.json()["case"]["status"] == "submitted"
    verified = client.get(f"/api/v2/cases/{case['case_id']}/verify", headers=headers)
    assert verified.status_code == 200
    assert verified.json()["valid"] is True
    received = client.post(
        f"/api/v2/cases/{case['case_id']}/events",
        headers=headers,
        json={"action": "receive", "expected_version": 2},
    )
    assert received.status_code == 200
    report = client.post(
        f"/api/v2/cases/{case['case_id']}/lab-reports",
        headers=headers,
        json={"laboratory": "Synthetic Lab", "outcome": "No controlled substance detected", "report_reference": "LAB-44"},
    )
    assert report.status_code == 200
    assert report.json()["case"]["lab_reports"][0]["report_reference"] == "LAB-44"
    stale = client.post(
        f"/api/v2/cases/{case['case_id']}/events",
        headers=headers,
        json={"action": "receive", "expected_version": 1},
    )
    assert stale.status_code == 409


def test_analysis_can_link_evidence_to_owned_case(client):
    headers = _auth(client)
    created = client.post("/api/v2/cases", headers=headers, json={"reference": "CASE-LINK", "title": "Linked evidence"})
    case_id = created.json()["case"]["case_id"]
    img = (DEMO_SAMPLES_DIR / "sample_alpha_positive.jpg").read_bytes()
    analyzed = client.post(
        "/api/analyze", headers=headers,
        files={"image": ("sample.jpg", io.BytesIO(img), "image/jpeg")},
        data={"profile_id": "SIM-PROFILE-ALPHA", "case_id": case_id},
    )
    assert analyzed.status_code == 200
    case = client.get(f"/api/v2/cases/{case_id}", headers=headers).json()["case"]
    assert analyzed.json()["test_id"] in case["evidence_test_ids"]
