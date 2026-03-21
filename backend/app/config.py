"""
Application settings via pydantic-settings.
All values can be overridden by environment variables or a .env file.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
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

    # Server
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    base_url: str = "http://localhost:8000"

    # Security
    secret_key: str = "change-me-to-a-random-64-char-string"
    session_cookie_name: str = "lti_session"
    session_max_age: int = 86400  # 24 hours

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/tutor.db"

    # LTI key files
    lti_private_key_file: str = "./data/lti_private.key"
    lti_public_key_file: str = "./data/lti_public.pem"

    # Open edX / LTI Platform
    openedx_issuer: str = "https://your-openedx-domain.com"
    openedx_client_id: str = "your-client-id"
    openedx_auth_endpoint: str = "https://your-openedx-domain.com/o/authorize"
    openedx_token_endpoint: str = "https://your-openedx-domain.com/o/token"
    openedx_jwks_endpoint: str = (
        "https://your-openedx-domain.com/api/lti_consumer/v1/public_keysets/"
    )

    # AI provider
    ai_provider: str = "gemini"  # gemini | ollama
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # CORS
    frontend_url: str = "http://localhost:5173"
    allowed_origins: str = "http://localhost:5173,http://localhost:8000"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def private_key_path(self) -> Path:
        return Path(self.lti_private_key_file)

    @property
    def public_key_path(self) -> Path:
        return Path(self.lti_public_key_file)

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
