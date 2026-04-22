"""Typed application settings.

Loaded from environment variables (and ``.env`` for local dev) via
pydantic-settings. ``get_settings`` is cached so the parsing cost is paid once.
Never read ``os.environ`` directly elsewhere — go through this module so all
config is discoverable in one place.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All env-driven config in one typed object.

    Add new fields here as features land. Keep them grouped by concern and
    documented inline so ``.env.example`` and this class never drift apart.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_env: str = "development"
    log_level: str = "INFO"

    # --- HTTP ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- WhatsApp (provider-specific; only the chosen provider's vars are used) ---
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_whatsapp_from: str | None = None

    meta_waba_phone_id: str | None = None
    meta_waba_token: str | None = None
    meta_waba_verify_token: str | None = None

    unipile_api_key: str | None = None
    unipile_dsn: str | None = None

    # --- Scraper / AI ---
    capsolver_api_key: str | None = None
    # Google ADK / Gemini drives the OCR fallback when Tesseract confidence is poor.
    google_api_key: str | None = None
    google_vision_model: str = "gemini-2.5-flash"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Cached accessor — first call parses env, every subsequent call is free."""
    return Settings()
