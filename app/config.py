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
    CORS_ORIGINS: str = "http://localhost:5173"

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
