"""
Runtime configuration via pydantic-settings / environment. Nothing hard-coded.
Port-sync contract values (PORT, CORS_ORIGINS) and InsForge secrets all come from env.
"""
import os
import sys
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEMO_SIGNING_KEY = "local-demo-evidence-key"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Port sync contract ---
    PORT: int = 8000
    # Allowed browser origins. "*" allows any origin (fine here — Bearer-token
    # auth, no cookies). Set a comma-separated allowlist to lock it down.
    CORS_ORIGINS: str = "*"
    # Demo mode deliberately leaves CORS open. It uses bearer headers, never cookies.
    CORS_ALLOW_CREDENTIALS: bool = False
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    # Replace in pilot/production; this default is suitable only for local simulated data.
    # PRODUCTION: set EVIDENCE_SIGNING_KEY to a strong random secret via your host's
    # secret manager (never commit the value). The server will refuse to start in
    # production while this is still the demo value.
    EVIDENCE_SIGNING_KEY: str = _DEMO_SIGNING_KEY

    # --- App ---
    APP_VERSION: str = "0.1.0"
    # Set NARCTRACE_ENV=production to enable production-mode guards (demo key refusal).
    NARCTRACE_ENV: str = "development"

    # --- Persistence backend selection: "local" | "insforge" ---
    STORE_BACKEND: str = "local"

    # --- InsForge (server-side secrets) ---
    INSFORGE_API_URL: str = ""
    INSFORGE_SERVICE_KEY: str = ""
    INSFORGE_EVIDENCE_BUCKET: str = "evidence"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.NARCTRACE_ENV.lower() == "production"


def _validate_production_settings(settings: "Settings") -> None:
    """Abort startup if unsafe defaults are used in production."""
    if not settings.is_production:
        return
    errors: list[str] = []
    if settings.EVIDENCE_SIGNING_KEY == _DEMO_SIGNING_KEY:
        errors.append(
            "EVIDENCE_SIGNING_KEY is still the public demo value. "
            "Set a strong random secret via your host's secret manager before deploying."
        )
    if errors:
        for msg in errors:
            print(f"[narctrace] FATAL: {msg}", file=sys.stderr)
        sys.exit(1)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    _validate_production_settings(s)
    return s
