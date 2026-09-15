# narctrace-backend

FastAPI backend for **NarcTrace** — a digital companion for field drug testing
(SIH26231). It runs a **deterministic** colour-science pipeline (OpenCV + scikit-image,
CIELAB D65 + CIEDE2000 ΔE — no ML/black-box) over a captured reaction photo and produces a
**tamper-evident evidence record** (Test ID `FT-#####`, SHA-256 image hash, timestamps,
operator, GPS, kit profile).

> **PRESUMPTIVE FIELD-TEST RESULT ONLY.** This software does not replace laboratory
> confirmatory testing. All kit profiles, thresholds, and target colour values are
> **SIMULATED / PROXY** values for safe demonstration. This application does NOT contain
> real narcotic test thresholds or proprietary reagent data.

---

## Run

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# dev
uvicorn app.main:app --reload --port 8000

# prod (Render)
gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:$PORT app.main:app
```

Health check: `GET http://localhost:8000/api/health` → `{"status":"ok","version":"0.1.0"}`.
Interactive docs at `/docs`.

Generate the synthetic demo/proxy samples (also done automatically by the test suite):

```bash
python scripts/generate_demo_samples.py --overwrite
```

## Tests

```bash
pytest            # 37 tests, no network required (STORE_BACKEND=local)
```

Coverage: quality gate, colour/calibration science, engine classification (incl.
Inconclusive), SHA-256 evidence hashing + `FT-#####` ids, LocalStore persistence/search,
full pipeline e2e on synthetic samples, and all API routes (FastAPI TestClient).

## Environment variables

All config comes from env (pydantic-settings). Copy `.env.example` → `.env` (gitignored).

| Var | Default | Purpose |
|-----|---------|---------|
| `PORT` | `8000` | Bind port (port-sync contract) |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins (never `*`) |
| `APP_VERSION` | `0.1.0` | Reported by `/api/health` |
| `STORE_BACKEND` | `local` | `local` (SQLite + filesystem, no creds) or `insforge` |
| `INSFORGE_API_URL` | — | InsForge project URL (insforge backend) |
| `INSFORGE_SERVICE_KEY` | — | Server-side service key — NEVER ship to frontend |
| `INSFORGE_EVIDENCE_BUCKET` | `evidence` | Storage bucket for evidence images |

### Persistence backends

A `Store` interface (`app/store/`) has two implementations, selected by `STORE_BACKEND`:

- **`local`** (default): SQLite (`data/evidence.db`) + evidence images under
  `data/evidence/`. Zero external credentials — for dev/CI and offline demos.
- **`insforge`**: InsForge DB table `evidence_records` (PRD §6), Storage bucket `evidence`,
  and InsForge Auth for `/api/auth/login`. Requires the `INSFORGE_*` vars.

The frontend never writes evidence directly; only the backend service key persists records.

## API contract (all routes under `/api`)

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/api/health` | — | `{status:"ok", version}` |
| POST | `/api/auth/login` | `{badge_id, password}` | `{token, officer:{id,name,badge_id}}` |
| GET | `/api/profiles` | — | `{success, profiles:[KitProfile]}` |
| POST | `/api/analyze` | multipart `image`, `profile_id`, `operator_id`, `gps` (JSON) — **Bearer** | `AnalysisResult` |
| GET | `/api/history?query=&result=&profile=` | Bearer | `{success, count, records:[EvidenceRecord]}` |
| GET | `/api/history/{test_id}` | Bearer | `{success, record}` |
| GET | `/api/evidence/{filename}` | Bearer | image bytes |

### `AnalysisResult` (POST `/api/analyze`)

```jsonc
{
  "success": true,
  "test_id": "FT-00001",
  "result": "Positive | Negative | Inconclusive",
  "quality": { "passed": true, "blur_score": 128.4, "exposure_status": "normal", "glare": false },
  "color":   { "hex": "#5b2d91", "lab": [..], "delta_e_positive": 3.1, "delta_e_negative": 41.0 },
  "profile": { "profile_id": "SIM-PROFILE-ALPHA", "name": "...", "version": "1.0-simulated" },
  "evidence": {
    "timestamp_utc": "2026-09-15T07:32:10Z",
    "timestamp_local": "2026-09-15 13:02:10",
    "operator_id": "FIELD-OP-01",
    "gps": { "lat": 28.61, "lon": 77.20, "label": "Delhi" },
    "image_sha256": "…",
    "image_url": "/api/evidence/FT-00001.jpg"
  },
  "disclaimer": "PRESUMPTIVE FIELD-TEST RESULT ONLY. …"
}
```

**Notes for the frontend**

- **Inconclusive is a first-class success result** — returned with HTTP 200 like
  Positive/Negative. A **quality-gate failure** (blur/exposure/glare/no-card) instead returns
  **HTTP 422** with `detail = {success:false, reason, quality, issues:[...], disclaimer}` —
  render `issues` as recapture guidance rather than a result.
- `gps` accepts either `{lat, lon, label}` or `{latitude, longitude, note}`; it is normalized
  to `{lat, lon, label}` (or `null` when coordinates are absent).
- `image_url` is a backend-served path (`/api/evidence/{test_id}.jpg`). Prefix it with
  `VITE_API_BASE` and send the Bearer token; the endpoint returns image bytes.
- `test_id` format is `FT-#####` (zero-padded, monotonic).
- History records are the persisted evidence shape: `{test_id, operator_id, result,
  profile_id, profile, timestamp_utc, timestamp_local, gps, color, quality, image_sha256,
  image_path, created_at}`.
- In `STORE_BACKEND=local`, `/api/auth/login` is a dev stub: any `badge_id` + non-empty
  `password` returns a token. Real officer auth is InsForge in production.

## Deploy

`render.yaml` defines a Render web service (`gunicorn` + Uvicorn workers, health check
`/api/health`). Set `CORS_ORIGINS`, `STORE_BACKEND=insforge`, and the `INSFORGE_*` secrets in
the Render dashboard.

## Port-sync contract

`PORT` / `CORS_ORIGINS` here must match the frontend's `VITE_API_BASE`. CI verifies with:

```bash
node scripts/check-ports-in-sync.mjs .env.example ../narctrace-frontend/.env.example
```
