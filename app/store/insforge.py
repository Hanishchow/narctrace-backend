"""
InsforgeStore — persistence + auth via InsForge BaaS (PRD §6).

Uses the InsForge REST API with the server-side service key:
- DB table `evidence_records` (schema per PRD §6)
- Storage bucket `evidence` (raw captured images, keyed by test_id)
- Auth for /api/auth/login (officer accounts)

Selected via STORE_BACKEND=insforge. Requires INSFORGE_API_URL + INSFORGE_SERVICE_KEY.
All network calls are guarded and surface as StoreError so the API can respond cleanly.

NOTE: InsForge REST paths can vary by project/version. Endpoint templates are centralized
below so they can be adjusted without touching call sites.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

import requests

from app.models import EvidenceRecord
from app.store.base import Store, AuthResult, StoreError

_TIMEOUT = 20


class InsforgeStore(Store):
    def __init__(self, api_url: str, service_key: str, bucket: str = "evidence"):
        if not api_url or not service_key:
            raise StoreError("InsForge backend requires INSFORGE_API_URL and INSFORGE_SERVICE_KEY")
        self.api_url = api_url.rstrip("/")
        self.service_key = service_key
        self.bucket = bucket
        self.table = "evidence_records"

    # --- HTTP helpers ---
    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.service_key}",
            "apikey": self.service_key,
        }
        if extra:
            h.update(extra)
        return h

    def _db_url(self) -> str:
        return f"{self.api_url}/database/records/{self.table}"

    def _storage_url(self, key: str) -> str:
        return f"{self.api_url}/storage/buckets/{self.bucket}/objects/{key}"

    # --- Test IDs ---
    def next_test_id(self) -> str:
        # Count existing records to produce a monotonic FT-##### id.
        try:
            resp = requests.get(
                self._db_url(),
                headers=self._headers(),
                params={"select": "test_id", "limit": 1000},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            rows = resp.json()
            n = len(rows) if isinstance(rows, list) else int(rows.get("count", 0))
        except Exception as e:  # pragma: no cover - network path
            raise StoreError(f"InsForge next_test_id failed: {e}") from e
        return f"FT-{n + 1:05d}"

    # --- Storage ---
    def save_evidence_image(self, test_id: str, image_bytes: bytes, content_type: str = "image/jpeg") -> str:
        key = f"{test_id}.jpg"
        try:
            resp = requests.put(
                self._storage_url(key),
                headers=self._headers({"Content-Type": content_type}),
                data=image_bytes,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
        except Exception as e:  # pragma: no cover
            raise StoreError(f"InsForge storage upload failed: {e}") from e
        return key

    def evidence_image_url(self, image_path: str) -> str:
        # Backend-served path issues a signed URL on demand via read; expose stable route.
        return f"/api/evidence/{image_path}"

    def read_evidence_bytes(self, filename: str) -> Optional[Tuple[bytes, str]]:
        try:
            resp = requests.get(
                self._storage_url(filename), headers=self._headers(), timeout=_TIMEOUT
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "image/jpeg")
            return resp.content, ctype
        except Exception as e:  # pragma: no cover
            raise StoreError(f"InsForge storage read failed: {e}") from e

    # --- Records ---
    def save_record(self, record: EvidenceRecord) -> None:
        payload = {
            "id": str(uuid.uuid4()),
            "test_id": record.test_id,
            "operator_id": record.operator_id,
            "result": record.result,
            "profile_id": record.profile_id,
            "timestamp_utc": record.timestamp_utc,
            "timestamp_local": record.timestamp_local,
            "gps": record.gps,
            "color": record.color,
            "quality": record.quality,
            "image_sha256": record.image_sha256,
            "image_path": record.image_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            resp = requests.post(self._db_url(), headers=self._headers(), json=payload, timeout=_TIMEOUT)
            resp.raise_for_status()
        except Exception as e:  # pragma: no cover
            raise StoreError(f"InsForge save_record failed: {e}") from e

    def _row_to_record_dict(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "test_id": row.get("test_id"),
            "operator_id": row.get("operator_id"),
            "result": row.get("result"),
            "profile_id": row.get("profile_id"),
            "profile": {"profile_id": row.get("profile_id"), "name": "", "version": ""},
            "timestamp_utc": row.get("timestamp_utc"),
            "timestamp_local": row.get("timestamp_local"),
            "gps": row.get("gps"),
            "color": row.get("color"),
            "quality": row.get("quality"),
            "image_sha256": row.get("image_sha256"),
            "image_path": row.get("image_path"),
            "created_at": row.get("created_at"),
        }

    def get_record(self, test_id: str) -> Optional[Dict[str, Any]]:
        try:
            resp = requests.get(
                self._db_url(), headers=self._headers(),
                params={"test_id": f"eq.{test_id}", "limit": 1}, timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            rows = resp.json()
        except Exception as e:  # pragma: no cover
            raise StoreError(f"InsForge get_record failed: {e}") from e
        if isinstance(rows, list) and rows:
            return self._row_to_record_dict(rows[0])
        return None

    def search_records(
        self,
        query: Optional[str] = None,
        result_filter: Optional[str] = None,
        profile_filter: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"order": "timestamp_utc.desc", "limit": limit}
        if result_filter and result_filter.lower() != "all":
            params["result"] = f"eq.{result_filter}"
        if profile_filter and profile_filter.lower() != "all":
            params["profile_id"] = f"eq.{profile_filter}"
        try:
            resp = requests.get(self._db_url(), headers=self._headers(), params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            rows = resp.json()
        except Exception as e:  # pragma: no cover
            raise StoreError(f"InsForge search_records failed: {e}") from e
        records = [self._row_to_record_dict(r) for r in rows] if isinstance(rows, list) else []
        if query and query.strip():
            q = query.strip().lower()
            records = [
                r for r in records
                if q in (r.get("test_id") or "").lower() or q in (r.get("operator_id") or "").lower()
            ]
        return records

    # --- Auth ---
    def authenticate(self, badge_id: str, password: str) -> AuthResult:
        try:
            resp = requests.post(
                f"{self.api_url}/auth/sessions",
                headers=self._headers(),
                json={"email": badge_id, "password": password},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # pragma: no cover
            raise StoreError(f"InsForge authentication failed: {e}") from e
        token = data.get("access_token") or data.get("token", "")
        user = data.get("user", {}) or {}
        return AuthResult(
            token=token,
            officer={
                "id": user.get("id", badge_id),
                "name": user.get("name", badge_id),
                "badge_id": badge_id,
            },
        )
