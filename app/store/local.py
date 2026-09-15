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
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from app.constants import EVIDENCE_DIR, DATA_DIR
from app.models import EvidenceRecord
from app.store.base import Store, AuthResult, StoreError

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
            conn.commit()

    # --- Test IDs ---
    def next_test_id(self) -> str:
        with self._conn() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) AS n FROM evidence_records")
            n = c.fetchone()["n"]
        return f"FT-{n + 1:05d}"

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
            c.execute(
                """
                INSERT OR REPLACE INTO evidence_records (
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
            conn.commit()

    def get_record(self, test_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            c = conn.cursor()
            c.execute("SELECT record_json FROM evidence_records WHERE test_id = ?", (test_id,))
            row = c.fetchone()
        return json.loads(row["record_json"]) if row else None

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
        token = hashlib.sha256(f"local-dev::{badge_id}".encode()).hexdigest()
        return AuthResult(
            token=token,
            officer={"id": f"local-{badge_id}", "name": f"Officer {badge_id}", "badge_id": badge_id},
        )
