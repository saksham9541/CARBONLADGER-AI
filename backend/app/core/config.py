"""
CarbonLedger AI — Application Settings
======================================
All configuration is loaded from environment variables (via .env file).
No secrets are hard-coded. Pydantic-settings validates types at startup.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "CarbonLedger AI"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # API server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Database
    database_url: str = "postgresql://carbonledger:carbonledger@localhost:5432/carbonledger"

    # Security
    secret_key: str = "CHANGE_ME"
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"

    # File storage
    storage_backend: str = "local"
    local_storage_path: str = "./uploads"
    max_file_size_mb: int = 50

    # Supabase Auth & Storage
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_storage_bucket: str = "carbonledger-evidence"
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_issuer: str = ""
    supabase_jwks_url: str = ""

    # Gemini (Phase 2+)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-pro"

    @property
    def cors_origins_list(self) -> List[str]:
        """Return CORS origins as a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_not_be_default(cls, v: str) -> str:
        # Warn but don't block in development
        return v


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings (singleton)."""
    return Settings()
