"""
Runtime configuration via pydantic-settings / environment. Nothing hard-coded.
Port-sync contract values (PORT, CORS_ORIGINS) and InsForge secrets all come from env.
"""
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    EVIDENCE_SIGNING_KEY: str = "local-demo-evidence-key"

    # --- App ---
    APP_VERSION: str = "0.1.0"

    # --- Persistence backend selection: "local" | "insforge" ---
    STORE_BACKEND: str = "local"

    # --- InsForge (server-side secrets) ---
    INSFORGE_API_URL: str = ""
    INSFORGE_SERVICE_KEY: str = ""
    INSFORGE_EVIDENCE_BUCKET: str = "evidence"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
