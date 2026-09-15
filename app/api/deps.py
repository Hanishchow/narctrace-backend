"""
Shared API dependencies: Store injection and Bearer-token guard.
"""
from fastapi import Header, HTTPException, status

from app.store import Store, get_store


def store_dep() -> Store:
    return get_store()


def require_bearer(authorization: str = Header(default="")) -> str:
    """
    Requires an `Authorization: Bearer <token>` header. The frontend obtains the token
    from /api/auth/login (InsForge Auth in prod, dev stub locally). Returns the raw token.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header (expected 'Bearer <token>').",
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Empty bearer token.")
    return token
