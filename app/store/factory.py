"""
Store selection via STORE_BACKEND env flag (default: local).
"""
from functools import lru_cache

from app.config import get_settings
from app.store.base import Store


@lru_cache
def get_store() -> Store:
    settings = get_settings()
    backend = (settings.STORE_BACKEND or "local").strip().lower()
    if backend == "insforge":
        from app.store.insforge import InsforgeStore
        return InsforgeStore(
            api_url=settings.INSFORGE_API_URL,
            service_key=settings.INSFORGE_SERVICE_KEY,
            bucket=settings.INSFORGE_EVIDENCE_BUCKET,
        )
    from app.store.local import LocalStore
    return LocalStore()
