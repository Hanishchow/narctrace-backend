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
    assert body["evidence"]["operator_id"] == "WEB-TESTER"
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


def test_history_requires_bearer(client):
    assert client.get("/api/history").status_code == 401


def test_evidence_missing_404(client):
    headers = _auth(client)
    assert client.get("/api/evidence/nope.jpg", headers=headers).status_code == 404
