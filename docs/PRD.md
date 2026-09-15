# NarcTrace — Product Requirements Document (PRD)

**Project:** NarcTrace — Digital Companion for Field Drug Testing
**Problem statement:** SIH26231 (Smart India Hackathon 2026)
**Owner:** N Hanish (GitHub: `Hanishchow`)
**Status:** v1 architecture locked · 2026-09-15
**Source references:**
- `Siddhagg/narctrace` — client-only UX reference (camera, GPS, colour capture flow)
- `Ashish2067/Technocrats-SIH26231` — deterministic CV backend reference (CIELAB, CIEDE2000, evidence, history)

> **Official Disclaimer (must appear in-product):** PRESUMPTIVE FIELD-TEST RESULT ONLY.
> This software does not replace laboratory confirmatory testing. All kit profiles,
> thresholds, and target colour values are **SIMULATED / PROXY** values for safe
> demonstration. This application does NOT contain real narcotic test thresholds or
> proprietary reagent data.

---

## 1. Problem & Goal

Field officers use colorimetric drug-test kits whose results are interpreted **by eye**,
which is subjective, unlogged, and non-traceable. NarcTrace is a **digital companion** that:

1. Guides the officer through a standardized photo capture of the test reaction.
2. Runs a **deterministic** colour-science pipeline (no ML/black-box) to classify the
   reaction as **Positive / Negative / Inconclusive**.
3. Produces a **tamper-evident digital evidence record** (Test ID, officer, UTC + local
   time, GPS, kit profile, SHA-256 image hash) stored in a searchable history.

**It assists, never replaces, confirmatory lab testing.** This positioning must be visible
in the UI at all times.

### Non-goals (v1)
- No claim of "100% AI detection". Deterministic colour science only.
- No real reagent data. Proxy profiles only.
- No polished/branded UI — visual design is intentionally simple now (see §7). A
  professional redesign is a later phase.

---

## 2. Architecture — Two-Repo Split

The system is split into **two separate GitHub repositories** for a security boundary:
the officer-facing client never holds server secrets or direct DB credentials, and the
CV/evidence logic is not shipped to the browser.

```
┌─────────────────────────┐        HTTPS / JSON + multipart        ┌──────────────────────────┐
│  narctrace-frontend      │ ───────────────────────────────────▶ │  narctrace-backend        │
│  React + Vite (static)   │                                       │  FastAPI (Python 3.10)    │
│  - camera capture        │ ◀─────────────────────────────────── │  - CV pipeline (OpenCV/   │
│  - GPS acquisition       │        analysis result + record       │    scikit-image)          │
│  - officer login (UI)    │                                       │  - CIEDE2000 ΔE engine    │
│  - history browser       │                                       │  - evidence + SHA-256     │
│  Port (dev): 5173        │                                       │  Port (dev): 8000         │
└─────────────────────────┘                                       └────────────┬─────────────┘
                                                                                │  SDK (server-side key)
                                                                   ┌────────────▼─────────────┐
                                                                   │  InsForge (BaaS)          │
                                                                   │  - Auth (officer accounts)│
                                                                   │  - DB  (evidence records) │
                                                                   │  - Storage (evidence imgs)│
                                                                   └──────────────────────────┘
```

### Why two repos (security rationale)
- **Secret isolation:** the InsForge **service/admin key** lives only in the backend repo's
  environment, never in frontend code (which is fully public once shipped to a browser).
- **Attack surface:** the CV pipeline, evidence hashing, and DB writes run server-side and
  are never exposed as client code.
- **Independent deploy & audit:** each repo has its own CI, review, and deploy cadence.
- The frontend authenticates the officer against InsForge Auth and receives a **short-lived
  user token**; all evidence writes go **through the backend**, which validates the token
  and applies the CV pipeline before persisting. The frontend never writes evidence
  records directly.

### Repositories
| Repo | Stack | Deploy target | Dev port |
|------|-------|---------------|----------|
| `narctrace-backend` | FastAPI + Uvicorn/Gunicorn, OpenCV-headless, scikit-image, InsForge SDK | Render (web service) | **8000** |
| `narctrace-frontend` | React 18 + Vite + TypeScript | Vercel / static host | **5173** |

---

## 3. Port Sync Contract (single source of truth)

Both repos MUST agree on these values. They are duplicated intentionally and verified by a
CI check (`scripts/check-ports-in-sync`) so drift fails the build.

| Setting | Backend | Frontend |
|---------|---------|----------|
| Backend base URL (dev) | binds `0.0.0.0:8000` | `VITE_API_BASE=http://localhost:8000` |
| Backend base URL (prod) | `$PORT` (Render) | `VITE_API_BASE=https://<backend-domain>` |
| CORS allowed origins | `CORS_ORIGINS` env = `http://localhost:5173,https://<frontend-domain>` | Vite dev server origin `http://localhost:5173` |
| API prefix | all routes under `/api` | every fetch prefixes `${VITE_API_BASE}/api` |
| Health check | `GET /api/health` → `{status:"ok"}` | frontend pings on boot; shows "backend unreachable" banner if down |

**Rule:** neither port nor origin is hard-coded in component/source files. Backend reads
`PORT` + `CORS_ORIGINS`; frontend reads `VITE_API_BASE`. A `.env.example` in each repo
documents them, and the two `.env.example` files are compared by the sync check.

---

## 4. API Contract (backend ⇄ frontend)

Ported and hardened from the Technocrats reference. All under `/api`. JSON unless noted.

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/api/health` | — | `{status:"ok", version}` |
| POST | `/api/auth/login` | `{badge_id, password}` (proxies InsForge Auth) | `{token, officer:{id,name,badge_id}}` |
| GET | `/api/profiles` | — | `{success, profiles:[KitProfile]}` |
| POST | `/api/analyze` | multipart: `image`, `profile_id`, `operator_id`, `gps` (JSON) — **Bearer token** | `AnalysisResult` (see below) |
| GET | `/api/history?query=&result=&profile=` | Bearer token | `{success, count, records:[EvidenceRecord]}` |
| GET | `/api/history/{test_id}` | Bearer token | `{success, record}` |
| GET | `/api/evidence/{filename}` | Bearer token | image bytes (or signed InsForge storage URL) |

### `AnalysisResult` (POST /api/analyze)
```jsonc
{
  "success": true,
  "test_id": "FT-00042",
  "result": "Positive | Negative | Inconclusive",
  "quality": { "passed": true, "blur_score": 128.4, "exposure_status": "normal", "glare": false },
  "color": { "hex": "#5b2d91", "lab": [..], "delta_e_positive": 3.1, "delta_e_negative": 41.0 },
  "profile": { "profile_id": "SIM-PROFILE-ALPHA", "name": "...", "version": "..." },
  "evidence": {
    "timestamp_utc": "2026-09-15T07:32:10Z",
    "timestamp_local": "...",
    "operator_id": "FIELD-OP-01",
    "gps": { "lat": .., "lon": .., "label": "city, state" },
    "image_sha256": "…",
    "image_url": "https://…insforge…/evidence/FT-00042.jpg"
  },
  "disclaimer": "PRESUMPTIVE FIELD-TEST RESULT ONLY. …"
}
```

**Inconclusive is a first-class result** — ambiguous reactions within `ambiguity_margin` of a
boundary, or out-of-bounds ΔE, classify as Inconclusive, never a forced Positive/Negative.

---

## 5. Backend requirements (`narctrace-backend`)

Port the deterministic pipeline from `Ashish2067/Technocrats-SIH26231`, re-homed on FastAPI:

- **Pipeline stages (unchanged science):** image quality gate (blur/Laplacian ≥ 75,
  exposure clipping, specular glare) → reference-card detection & perspective normalize →
  white-patch illuminant calibration → RGB→CIELAB (D65) → CIEDE2000 ΔE → kit-profile rules
  → result engine (Positive/Negative/Inconclusive).
- **Kit profiles:** JSON in `data/profiles/*.json` (Alpha = Purple proxy, Beta = Cobalt Blue
  proxy). All SIMULATED/PROXY.
- **Evidence:** SHA-256 over raw image bytes; record assembled with Test ID, timestamps,
  operator, GPS, profile, hash.
- **Persistence → InsForge (replaces local SQLite):**
  - `evidence_records` table (schema §6) via InsForge DB.
  - Evidence images → InsForge Storage bucket `evidence`.
  - Officer accounts → InsForge Auth.
- **Framework:** FastAPI, Pydantic models mirroring the reference dataclasses, async where it
  helps, Uvicorn (dev) / Gunicorn+Uvicorn workers (prod).
- **Config:** all secrets from env (`INSFORGE_API_URL`, `INSFORGE_SERVICE_KEY`, `CORS_ORIGINS`,
  `PORT`). Nothing hard-coded. `.env.example` committed; `.env` gitignored.
- **CORS:** restricted to `CORS_ORIGINS`. No `*` in production.
- **Tests:** port the reference's deterministic unit/integration suite (quality, colour,
  engine, evidence, pipeline, API) to pytest. Target ≥ the reference's coverage of core
  modules. CV maths must be verified on synthetic samples (no live camera in CI).
- **Health:** `GET /api/health`.

---

## 6. InsForge data model

**Auth:** InsForge Auth manages officers. Officer profile fields: `name`, `badge_id` (unique).

**DB table `evidence_records`:**
| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid (pk) | |
| `test_id` | text unique | `FT-#####` |
| `operator_id` | text | officer badge/ID |
| `result` | text | Positive/Negative/Inconclusive |
| `profile_id` | text | kit profile used |
| `timestamp_utc` | timestamptz | |
| `timestamp_local` | text | |
| `gps` | jsonb | `{lat,lon,label}` nullable |
| `color` | jsonb | hex/lab/ΔE metrics |
| `quality` | jsonb | blur/exposure/glare telemetry |
| `image_sha256` | text | integrity hash |
| `image_path` | text | storage key in `evidence` bucket |
| `created_at` | timestamptz | default now() |

**Storage bucket `evidence`:** raw captured images, keyed by `test_id`. Access via
backend-issued signed URLs only.

**Access rule:** frontend never writes this table directly. Only the backend service key
writes. Reads for history go through the backend (token-validated).

---

## 7. Design rules (kept deliberately simple — pro redesign is a later phase)

These are the v1 rules. They will be pushed to a Claude Design project via `/design-sync`
once the frontend component library exists (Button, Field, ResultBadge, EvidenceCard,
CameraFrame, HistoryRow), so design and code stay in sync.

**Principles**
1. **Clarity over decoration.** This is field-evidence software; legibility and trust beat
   visual flourish. No gradients-for-gradients'-sake, no glassmorphism in v1.
2. **Result is unmistakable.** Positive / Negative / Inconclusive must be readable at a
   glance in sunlight — large type, high contrast, colour + text + icon (never colour alone,
   for accessibility).
3. **Disclaimer always visible.** The presumptive-only disclaimer is persistent, not a
   dismissible toast.
4. **One task per screen.** Login → Start test → Capture → Result → History. No dense dashboards.

**Tokens (v1)**
- **Colour:** neutral base (white / near-black text). Semantic only for results —
  Positive `#0F7B4E` (green), Negative `#B42318` (red), Inconclusive `#B54708` (amber).
  Never use these hues decoratively elsewhere.
- **Type:** system UI stack (`-apple-system, Segoe UI, Roboto, sans-serif`). Scale:
  32/24/18/16/14. Result badge uses the 32.
- **Spacing:** 4px base grid (4/8/12/16/24/32).
- **Radius:** 8px cards, 6px controls. **Shadow:** one soft elevation only.
- **Targets:** min 44×44px tap targets (field use, gloves/outdoors).
- **Motion:** minimal — 150ms ease for state changes only. Respect `prefers-reduced-motion`.
- **Accessibility:** WCAG AA contrast; colour never the sole signal; keyboard reachable.

**Frontend structure**
- React + Vite + TypeScript. Components in `src/components`, screens in `src/screens`,
  API client in `src/api/client.ts` (single place that reads `VITE_API_BASE`).
- No component hard-codes a colour hex — all via CSS variables / tokens file
  `src/styles/tokens.css` so the later pro redesign only swaps tokens.

---

## 8. Milestones & task breakdown (orchestration)

| # | Task | Owner | Depends on |
|---|------|-------|-----------|
| T1 | PRD + architecture + contracts (this doc) | Apollo | — |
| T2 | Scaffold both repos + port-sync contract + `.env.example` + CI sync check | Apollo | T1 |
| T3 | Backend: port CV pipeline → FastAPI, Pydantic models, tests | backend agent | T2 |
| T4 | Backend: InsForge integration (auth, DB, storage) | backend agent | T3 |
| T5 | Frontend: React+Vite app — login, capture, result, history against API | frontend agent | T2 |
| T6 | Integration: run both, verify ports in sync + full flow on demo samples | Apollo (review) | T3–T5 |
| T7 | Create 2 GitHub repos under `Hanishchow`, push, wire CI | Apollo | T6 |
| T8 | `/design-sync` push of component library to Claude Design project | Apollo | T5 |

**Definition of done (v1)**
- Both servers boot; `GET /api/health` green; frontend shows no "backend unreachable" banner.
- Full flow works end-to-end on the 5 demo proxy samples (Alpha +/−/inconclusive, Beta +,
  blurry rejection) with correct classifications.
- Evidence records persist to InsForge; images in InsForge Storage; history reads back.
- Backend test suite green. No secret in the frontend bundle. CORS locked to known origins.
- Ports-in-sync CI check passes.
</content>
