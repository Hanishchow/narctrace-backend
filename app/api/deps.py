"""
Shared API dependencies: Store injection and Bearer-token guard.
"""
from typing import Dict, Any

from fastapi import Depends, Header, HTTPException, status

from app.store import Store, get_store


def store_dep() -> Store:
    return get_store()


def require_actor(
    authorization: str = Header(default=""),
    store: Store = Depends(store_dep),
) -> Dict[str, Any]:
    """
    Requires and verifies an Authorization bearer token. A non-empty value is not
    sufficient: the active storage/auth provider must return a verified actor.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header (expected 'Bearer <token>').",
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Empty bearer token.")
    actor = store.actor_from_token(token)
    if not actor:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired bearer token.")
    return actor


def require_bearer(actor: Dict[str, Any] = Depends(require_actor)) -> str:
    """Legacy dependency retained for endpoint compatibility."""
    return str(actor.get("badge_id") or actor.get("id") or "")
