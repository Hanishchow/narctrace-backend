"""
LocalStore — SQLite + local filesystem fallback (zero external credentials).
Lets the app run fully for dev/CI with STORE_BACKEND=local. Evidence images are written
under data/evidence/ and served back through the backend /api/evidence route.

Local auth is a DEV STUB: any badge_id + non-empty password succeeds, returning a
deterministic pseudo-token. Real officer auth is handled by InsForge in production.
"""
import json
import sqlite3
import hashlib
import hmac
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from app.constants import EVIDENCE_DIR, DATA_DIR
from app.models import EvidenceRecord
from app.store.base import Store, AuthResult, StoreError
from app.config import get_settings
from app.passport import canonical_manifest, custody_event_hash, sign_manifest

DB_PATH = DATA_DIR / "evidence.db"


class LocalStore(Store):
    def __init__(self, db_path: Path = DB_PATH, evidence_dir: Path = EVIDENCE_DIR):
        self.db_path = db_path
        self.evidence_dir = evidence_dir
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            c = conn.cursor()
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_records (
                    test_id TEXT PRIMARY KEY,
                    operator_id TEXT NOT NULL,
                    result TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    timestamp_local TEXT NOT NULL,
                    image_sha256 TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    record_json TEXT NOT NULL
                )
                """
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_result ON evidence_records(result)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_profile ON evidence_records(profile_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_operator ON evidence_records(operator_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_ts ON evidence_records(timestamp_utc DESC)")
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS test_id_sequence (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    value INTEGER NOT NULL
                )
                """
            )
            c.execute("INSERT OR IGNORE INTO test_id_sequence (singleton, value) VALUES (1, 0)")
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency_receipts (
                    key TEXT PRIMARY KEY,
                    payload_hash TEXT NOT NULL,
                    test_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    reference TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    owner_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS custody_events (
                    event_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    previous_hash TEXT NOT NULL DEFAULT '',
                    event_hash TEXT NOT NULL DEFAULT '',
                    UNIQUE(case_id, sequence)
                )
                """
            )
            for column in ("previous_hash TEXT NOT NULL DEFAULT ''", "event_hash TEXT NOT NULL DEFAULT ''"):
                try:
                    c.execute(f"ALTER TABLE custody_events ADD COLUMN {column}")
                except sqlite3.OperationalError:
                    pass
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_manifests (
                    test_id TEXT PRIMARY KEY,
                    manifest TEXT NOT NULL,
                    signature TEXT NOT NULL
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS lab_reports (
                    report_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    laboratory TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    report_reference TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS case_evidence (
                    case_id TEXT NOT NULL,
                    test_id TEXT NOT NULL UNIQUE,
                    PRIMARY KEY (case_id, test_id)
                )
                """
            )
            conn.commit()

    # --- Test IDs ---
    def next_test_id(self) -> str:
        with self._conn() as conn:
            c = conn.cursor()
            # BEGIN IMMEDIATE serializes allocators across SQLite connections.
            # Gaps after a failed upload are acceptable; reused evidence IDs are not.
            c.execute("BEGIN IMMEDIATE")
            c.execute("UPDATE test_id_sequence SET value = value + 1 WHERE singleton = 1")
            c.execute("SELECT value FROM test_id_sequence WHERE singleton = 1")
            value = c.fetchone()["value"]
            conn.commit()
        return f"FT-{value:05d}"

    # --- Storage ---
    def save_evidence_image(self, test_id: str, image_bytes: bytes, content_type: str = "image/jpeg") -> str:
        filename = f"{test_id}.jpg"
        (self.evidence_dir / filename).write_bytes(image_bytes)
        return filename

    def evidence_image_url(self, image_path: str) -> str:
        # Backend-served path (frontend prefixes VITE_API_BASE).
        return f"/api/evidence/{image_path}"

    def read_evidence_bytes(self, filename: str) -> Optional[Tuple[bytes, str]]:
        # Guard against path traversal.
        safe = Path(filename).name
        path = self.evidence_dir / safe
        if path.is_file():
            return path.read_bytes(), "image/jpeg"
        return None

    # --- Records ---
    def save_record(self, record: EvidenceRecord) -> None:
        d = record.to_dict()
        with self._conn() as conn:
            c = conn.cursor()
            try:
                c.execute(
                    """
                    INSERT INTO evidence_records (
                        test_id, operator_id, result, profile_id, timestamp_utc,
                        timestamp_local, image_sha256, image_path, created_at, record_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.test_id, record.operator_id, record.result, record.profile_id,
                        record.timestamp_utc, record.timestamp_local, record.image_sha256,
                        record.image_path, record.created_at, json.dumps(d),
                    ),
                )
                manifest = canonical_manifest(d)
                c.execute(
                    "INSERT INTO evidence_manifests (test_id, manifest, signature) VALUES (?, ?, ?)",
                    (record.test_id, manifest, sign_manifest(manifest, get_settings().EVIDENCE_SIGNING_KEY)),
                )
                conn.commit()
            except sqlite3.IntegrityError as e:
                raise StoreError(f"Evidence record already exists: {record.test_id}") from e

    def get_record(self, test_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            c = conn.cursor()
            c.execute("SELECT record_json FROM evidence_records WHERE test_id = ?", (test_id,))
            row = c.fetchone()
        return json.loads(row["record_json"]) if row else None

    def get_evidence_manifest(self, test_id: str) -> Optional[Dict[str, str]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT manifest, signature FROM evidence_manifests WHERE test_id = ?", (test_id,)
            ).fetchone()
        return dict(row) if row else None

    def search_records(
        self,
        query: Optional[str] = None,
        result_filter: Optional[str] = None,
        profile_filter: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        conditions, params = [], []
        if query and query.strip():
            q = f"%{query.strip()}%"
            conditions.append("(test_id LIKE ? OR operator_id LIKE ?)")
            params.extend([q, q])
        if result_filter and result_filter.strip() and result_filter.lower() != "all":
            conditions.append("result = ?")
            params.append(result_filter.strip())
        if profile_filter and profile_filter.strip() and profile_filter.lower() != "all":
            conditions.append("profile_id = ?")
            params.append(profile_filter.strip())

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT record_json FROM evidence_records{where} ORDER BY timestamp_utc DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            c = conn.cursor()
            c.execute(sql, params)
            rows = c.fetchall()
        return [json.loads(r["record_json"]) for r in rows]

    # --- Auth (dev stub) ---
    def authenticate(self, badge_id: str, password: str) -> AuthResult:
        badge_id = (badge_id or "").strip()
        if not badge_id or not (password or "").strip():
            raise StoreError("badge_id and password are required")
        digest = hashlib.sha256(f"local-dev::{badge_id}".encode()).hexdigest()
        token = f"local-dev.{badge_id}.{digest}"
        return AuthResult(
            token=token,
            officer={"id": f"local-{badge_id}", "name": f"Officer {badge_id}", "badge_id": badge_id},
        )

    def actor_from_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verifies the locally-issued demo token using constant-time comparison."""
        prefix, separator, digest = token.rpartition(".")
        if not separator or not prefix.startswith("local-dev."):
            return None
        badge_id = prefix.removeprefix("local-dev.").strip()
        if not badge_id or "." in badge_id:
            return None
        expected = hashlib.sha256(f"local-dev::{badge_id}".encode()).hexdigest()
        if not hmac.compare_digest(digest, expected):
            return None
        return {"id": f"local-{badge_id}", "name": f"Officer {badge_id}", "badge_id": badge_id}

    def claim_idempotency(self, key: str, payload_hash: str, test_id: str) -> Dict[str, Any]:
        with self._conn() as conn:
            c = conn.cursor()
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                "SELECT payload_hash, test_id, status FROM idempotency_receipts WHERE key = ?",
                (key,),
            )
            existing = c.fetchone()
            if existing:
                conn.commit()
                return {"created": False, **dict(existing)}
            c.execute(
                "INSERT INTO idempotency_receipts (key, payload_hash, test_id, status) VALUES (?, ?, ?, 'pending')",
                (key, payload_hash, test_id),
            )
            conn.commit()
        return {"created": True, "payload_hash": payload_hash, "test_id": test_id, "status": "pending"}

    def finalize_idempotency(self, key: str) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE idempotency_receipts SET status = 'accepted' WHERE key = ?", (key,))
            conn.commit()

    def create_case(self, reference: str, title: str, actor_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        case = {
            "case_id": str(uuid.uuid4()), "reference": reference.strip(), "title": title.strip(),
            "status": "open", "version": 1, "owner_id": actor_id, "created_at": now, "updated_at": now,
        }
        if not case["reference"] or not case["title"]:
            raise StoreError("Case reference and title are required.")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO cases (case_id, reference, title, status, version, owner_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(case.values()),
            )
            event_hash = custody_event_hash(case["case_id"], 1, "created", actor_id, now, "", get_settings().EVIDENCE_SIGNING_KEY)
            conn.execute(
                "INSERT INTO custody_events (event_id, case_id, sequence, action, actor_id, created_at, previous_hash, event_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), case["case_id"], 1, "created", actor_id, now, "", event_hash),
            )
            conn.commit()
        return {**case, "events": [{"sequence": 1, "action": "created", "actor_id": actor_id, "created_at": now, "previous_hash": "", "event_hash": event_hash}]}

    def list_cases(self, actor_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT case_id, reference, title, status, version, owner_id, created_at, updated_at FROM cases WHERE owner_id = ? ORDER BY updated_at DESC",
                (actor_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT case_id, reference, title, status, version, owner_id, created_at, updated_at FROM cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            if not row:
                return None
            events = conn.execute(
                "SELECT sequence, action, actor_id, created_at, previous_hash, event_hash FROM custody_events WHERE case_id = ? ORDER BY sequence",
                (case_id,),
            ).fetchall()
            reports = conn.execute(
                "SELECT report_id, laboratory, outcome, report_reference, actor_id, created_at FROM lab_reports WHERE case_id = ? ORDER BY created_at",
                (case_id,),
            ).fetchall()
            evidence = conn.execute(
                "SELECT test_id FROM case_evidence WHERE case_id = ? ORDER BY test_id", (case_id,)
            ).fetchall()
        return {
            **dict(row), "events": [dict(event) for event in events],
            "lab_reports": [dict(report) for report in reports],
            "evidence_test_ids": [item["test_id"] for item in evidence],
        }

    def transition_case(self, case_id: str, action: str, actor_id: str, expected_version: int) -> Dict[str, Any]:
        transitions = {
            ("open", "submit"): "submitted", ("submitted", "receive"): "received_by_lab",
            ("received_by_lab", "review"): "reviewed", ("reviewed", "close"): "closed",
        }
        with self._conn() as conn:
            c = conn.cursor()
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
            if not row:
                raise StoreError("Case was not found.")
            case = dict(row)
            if case["owner_id"] != actor_id:
                raise StoreError("You are not assigned to this case.")
            if case["version"] != expected_version:
                raise StoreError("Case has changed. Refresh before applying this action.")
            new_status = transitions.get((case["status"], action))
            if not new_status:
                raise StoreError(f"Action '{action}' is not valid while case is {case['status']}.")
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            new_version = expected_version + 1
            c.execute("UPDATE cases SET status = ?, version = ?, updated_at = ? WHERE case_id = ?", (new_status, new_version, now, case_id))
            sequence = c.execute("SELECT COALESCE(MAX(sequence), 0) + 1 AS n FROM custody_events WHERE case_id = ?", (case_id,)).fetchone()["n"]
            previous = c.execute(
                "SELECT event_hash FROM custody_events WHERE case_id = ? ORDER BY sequence DESC LIMIT 1", (case_id,)
            ).fetchone()
            previous_hash = previous["event_hash"] if previous else ""
            event_hash = custody_event_hash(case_id, sequence, action, actor_id, now, previous_hash, get_settings().EVIDENCE_SIGNING_KEY)
            c.execute(
                "INSERT INTO custody_events (event_id, case_id, sequence, action, actor_id, created_at, previous_hash, event_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), case_id, sequence, action, actor_id, now, previous_hash, event_hash),
            )
            conn.commit()
        return self.get_case(case_id) or {}

    def add_lab_report(
        self, case_id: str, laboratory: str, outcome: str, report_reference: str, actor_id: str
    ) -> Dict[str, Any]:
        laboratory, outcome, report_reference = laboratory.strip(), outcome.strip(), report_reference.strip()
        if not laboratory or not outcome or not report_reference:
            raise StoreError("Laboratory, outcome, and report reference are required.")
        with self._conn() as conn:
            case = conn.execute("SELECT owner_id FROM cases WHERE case_id = ?", (case_id,)).fetchone()
            if not case or case["owner_id"] != actor_id:
                raise StoreError("You are not assigned to this case.")
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "INSERT INTO lab_reports (report_id, case_id, laboratory, outcome, report_reference, actor_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), case_id, laboratory, outcome, report_reference, actor_id, now),
            )
            conn.commit()
        return self.get_case(case_id) or {}

    def link_evidence_to_case(self, case_id: str, test_id: str, actor_id: str) -> None:
        with self._conn() as conn:
            case = conn.execute("SELECT owner_id FROM cases WHERE case_id = ?", (case_id,)).fetchone()
            if not case or case["owner_id"] != actor_id:
                raise StoreError("You are not assigned to this case.")
            conn.execute("INSERT INTO case_evidence (case_id, test_id) VALUES (?, ?)", (case_id, test_id))
            conn.commit()
