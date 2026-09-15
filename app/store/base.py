"""
Persistence abstraction. Two implementations exist behind this interface:
- LocalStore   : SQLite + local filesystem (zero external creds, for dev/CI).
- InsforgeStore: InsForge DB + Storage + Auth (PRD §6), selected via STORE_BACKEND=insforge.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

from app.models import EvidenceRecord


class StoreError(Exception):
    """Raised on persistence/auth failures."""


@dataclass
class AuthResult:
    token: str
    officer: Dict[str, Any]  # {id, name, badge_id}


class Store(ABC):
    """Backend-agnostic persistence + auth interface."""

    @abstractmethod
    def next_test_id(self) -> str:
        """Returns the next `FT-#####` test id (monotonic)."""

    @abstractmethod
    def save_evidence_image(self, test_id: str, image_bytes: bytes, content_type: str = "image/jpeg") -> str:
        """Persists raw image bytes; returns a storage key/path (image_path)."""

    @abstractmethod
    def evidence_image_url(self, image_path: str) -> str:
        """Returns a URL (or backend-served path) for an evidence image key."""

    @abstractmethod
    def save_record(self, record: EvidenceRecord) -> None:
        """Persists an evidence record."""

    @abstractmethod
    def get_record(self, test_id: str) -> Optional[Dict[str, Any]]:
        """Fetches one record dict by test_id, or None."""

    @abstractmethod
    def search_records(
        self,
        query: Optional[str] = None,
        result_filter: Optional[str] = None,
        profile_filter: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Filtered, newest-first list of record dicts."""

    @abstractmethod
    def read_evidence_bytes(self, filename: str) -> Optional[Tuple[bytes, str]]:
        """Returns (bytes, content_type) for a stored evidence file, or None if absent."""

    @abstractmethod
    def authenticate(self, badge_id: str, password: str) -> AuthResult:
        """Authenticates an officer. Raises StoreError on failure."""
