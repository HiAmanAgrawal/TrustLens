"""
Typed application settings — single source of truth for all configuration.

All environment variables flow through this module. Never read ``os.environ``
directly elsewhere; doing so creates invisible coupling and makes config
untestable. Call ``get_settings()`` and access a typed field instead.

``@lru_cache`` means the env file is parsed exactly once per process. Tests
that need different values should use ``get_settings.cache_clear()`` +
dependency override, not monkeypatching os.environ mid-flight.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Search for .env in the current working directory first, then one level up
    # (repo root). This lets the server be started from either backend/ or the
    # project root without needing a separate env file in each location.
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -----------------------------------------------------------------------
    # App
    # -----------------------------------------------------------------------
    app_env: str = "development"
    app_name: str = "TrustLens"
    app_version: str = "0.2.0"
    log_level: str = "INFO"

    # -----------------------------------------------------------------------
    # HTTP server
    # -----------------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # -----------------------------------------------------------------------
    # Database (Supabase / PostgreSQL + pgvector)
    # -----------------------------------------------------------------------
    # Full async DSN, e.g. postgresql+asyncpg://user:pass@host:5432/dbname
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trustlens"
    # Used by Alembic (sync driver) — swap asyncpg → psycopg2 automatically.
    # Alembic's env.py derives this from database_url; leave empty to let it do so.
    database_url_sync: str | None = None

    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30        # seconds

    # -----------------------------------------------------------------------
    # Redis (session / in-memory agent state)
    # -----------------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    session_ttl_seconds: int = 3600  # 1 hour per WhatsApp session

    # -----------------------------------------------------------------------
    # WhatsApp — Twilio
    # -----------------------------------------------------------------------
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_whatsapp_from: str | None = None   # e.g. whatsapp:+14155238886

    # -----------------------------------------------------------------------
    # WhatsApp — Meta Cloud API
    # -----------------------------------------------------------------------
    meta_waba_phone_id: str | None = None
    meta_waba_token: str | None = None
    meta_waba_verify_token: str | None = None

    # -----------------------------------------------------------------------
    # WhatsApp — Unipile
    # -----------------------------------------------------------------------
    unipile_api_key: str | None = None
    unipile_dsn: str | None = None

    # -----------------------------------------------------------------------
    # AI / ML
    # -----------------------------------------------------------------------
    # Google Gemini — primary OCR pass for medicine labels and grocery packs.
    # Tesseract is the local fallback if this key is absent or Gemini fails.
    google_api_key: str | None = None
    google_vision_model: str = "gemini-2.5-flash"

    # Anthropic Claude — product advisor agent backbone
    anthropic_api_key: str | None = None

    # -----------------------------------------------------------------------
    # LM Studio (local OpenAI-compatible server)
    #
    # Run a local vision model for product label extraction without sending
    # images to external APIs. Qwen2.5-VL / Qwen3-VL are recommended.
    #
    #   LM_STUDIO_BASE_URL=http://localhost:1234/v1
    #   LM_STUDIO_VISION_MODEL=qwen2.5-vl-7b-instruct   # match what's loaded
    #   LM_STUDIO_CHAT_MODEL=qwen3-8b                    # for product advisor
    #
    # LM Studio ignores the API key value — set any non-empty string.
    # -----------------------------------------------------------------------
    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_vision_model: str = "qwen2.5-vl-7b-instruct"
    lm_studio_chat_model: str = "qwen3-8b"
    lm_studio_api_key: str = "lm-studio"                  # any non-empty value works
    lm_studio_timeout_s: float = 60.0                     # vision inference can be slow locally
    lm_studio_health_timeout_s: float = 2.0               # quick ping before sending full request

    # OpenAI-compatible embedding endpoint (can be pointed at Supabase's
    # pgvector-compatible embedder or any local model).
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536
    openai_api_key: str | None = None

    # -----------------------------------------------------------------------
    # LangChain / LangGraph
    # -----------------------------------------------------------------------
    langchain_tracing_v2: bool = False
    langchain_api_key: str | None = None
    langchain_project: str = "trustlens"

    # -----------------------------------------------------------------------
    # Tavily (web search)
    # -----------------------------------------------------------------------
    tavily_api_key: str | None = None
    tavily_max_results: int = 5

    # -----------------------------------------------------------------------
    # Scraper
    # -----------------------------------------------------------------------
    capsolver_api_key: str | None = None
    scraper_timeout_s: float = 30.0

    # -----------------------------------------------------------------------
    # i18n — static catalogues
    # -----------------------------------------------------------------------
    default_language: str = "en"
    supported_languages: list[str] = ["en", "hi", "ta", "mr"]

    # -----------------------------------------------------------------------
    # i18n — AI-powered translation
    #
    # When USE_AI_I18N=true, conversational strings (WhatsApp replies,
    # summaries, help text) are translated on-the-fly by an AI model.
    # Safety-critical strings (verdicts, allergen/interaction warnings)
    # ALWAYS use the static JSON catalogue regardless of this flag.
    #
    # Supported providers:
    #   "gemini"   — Google Gemini via google-genai SDK (uses GOOGLE_API_KEY)
    #   "lmstudio" — any local OpenAI-compatible server (LM Studio, Ollama,
    #                llama.cpp) pointed at OPENAI_BASE_URL
    #   "openai"   — OpenAI cloud API
    # -----------------------------------------------------------------------
    use_ai_i18n: bool = False
    i18n_ai_provider: str = "gemini"      # gemini | lmstudio | openai
    i18n_ai_model: str = "gemini-2.5-flash"   # fast model for translation / rephrasing
    # Base URL for OpenAI-compatible endpoints.
    # LM Studio default: http://localhost:1234/v1
    # Ollama default:    http://localhost:11434/v1
    openai_base_url: str = "https://api.openai.com/v1"
    # In-process LRU cache size for AI translations (key+lang → translated string).
    # Prevents redundant API calls for identical WhatsApp reply templates.
    i18n_cache_size: int = 512

    # -----------------------------------------------------------------------
    # Feature flags  (simple booleans; no external flag service needed yet)
    # -----------------------------------------------------------------------
    enable_llm_summaries: bool = False   # Gate LLM-generated verdict summaries
    enable_web_search: bool = True       # Tavily for unknown products

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def sync_database_url(self) -> str:
        """Alembic uses a sync driver; swap asyncpg → psycopg2."""
        if self.database_url_sync:
            return self.database_url_sync
        return self.database_url.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        )


@lru_cache
def get_settings() -> Settings:
    """Cached accessor — first call parses the env file, every subsequent call is free."""
    return Settings()
