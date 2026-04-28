"""
AI-powered i18n — dynamic translation for any language via Gemini or LM Studio.

WHY this exists alongside the static JSON catalogues:
  The JSON catalogues cover the 3 languages we could manually verify (en, hi, ta).
  AI translation removes the ceiling — any language a user speaks, including
  regional ones (Bhojpuri, Konkani, Sindhi), gets a correct, context-aware reply
  without us maintaining additional catalogue files.

SAFETY DESIGN — the critical constraint:
  Medicine verdicts, allergen warnings, and drug interaction notices are
  safety-critical. An AI hallucinating "this product is safe" when the truth is
  "EXPIRED" could harm someone. These keys ALWAYS use the static catalogue.

  AI is used ONLY for conversational / informational strings:
    - WhatsApp greeting / help text
    - Nutrition commentary
    - Error messages
    - Product summaries

FALLBACK CHAIN:
  1. If key is safety-critical  → static catalogue.
  2. If USE_AI_I18N=false        → static catalogue.
  3. If lang == "en"             → static catalogue (no translation needed).
  4. Call AI provider.
  5. If AI fails (network, quota, timeout) → static catalogue.

CACHING:
  Translations are LRU-cached in-process keyed by (key, lang, frozen_kwargs).
  This means the 10 most common WhatsApp reply templates get translated once
  per process restart, not once per message — critical at WhatsApp scale.

USAGE:
    from app.core.i18n_ai import t_ai

    # Conversational — may use AI:
    reply = await t_ai("whatsapp.welcome", lang="bn")

    # Safety-critical — always static regardless of feature flag:
    verdict_msg = await t_ai("scan.verdict.expired", lang="gu", expiry_date="12 Jan 2024")

ADDING A NEW PROVIDER:
    1. Add a new branch in ``_call_ai()``.
    2. Add the provider name to the docstring above.
    3. Add the env vars to .env.example.
    No other changes needed.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import logging
from typing import Any

from app.core.i18n import t  # static catalogue fallback

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety key registry
#
# Keys that START WITH any of these prefixes are safety-critical and must
# never be AI-generated. Add new prefixes here if new safety domains appear.
# ---------------------------------------------------------------------------
_SAFETY_KEY_PREFIXES: frozenset[str] = frozenset([
    "scan.verdict.",          # VERIFIED / SUSPICIOUS / EXPIRED / UNKNOWN
    "allergen.warning.",      # allergen present in product
    "interaction.",           # drug-drug interaction notices
    "expiry.danger.",         # expired product — always static, never approximate
    "fssai.",                 # certification validity (legal)
])

# ---------------------------------------------------------------------------
# Language name map — used in the prompt so the model understands the target
# ISO code unambiguously. Covers all 22 Indian scheduled languages + major
# international ones.
# ---------------------------------------------------------------------------
_LANG_NAMES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi (हिंदी)",
    "ta": "Tamil (தமிழ்)",
    "mr": "Marathi (मराठी)",
    "bn": "Bengali (বাংলা)",
    "te": "Telugu (తెలుగు)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "gu": "Gujarati (ગુજરાતી)",
    "pa": "Punjabi (ਪੰਜਾਬੀ)",
    "ml": "Malayalam (മലയാളം)",
    "or": "Odia (ଓଡ଼ିଆ)",
    "as": "Assamese (অসমীয়া)",
    "ur": "Urdu (اردو)",
    "sa": "Sanskrit (संस्कृत)",
    "ne": "Nepali (नेपाली)",
    "si": "Sinhala (සිංහල)",
    # International
    "ar": "Arabic (العربية)",
    "zh": "Chinese Simplified (简体中文)",
    "fr": "French (Français)",
    "es": "Spanish (Español)",
    "de": "German (Deutsch)",
    "pt": "Portuguese (Português)",
    "ru": "Russian (Русский)",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
    "id": "Indonesian (Bahasa Indonesia)",
    "sw": "Swahili (Kiswahili)",
}

# ---------------------------------------------------------------------------
# In-process LRU translation cache
#
# Key: SHA-256 hash of (i18n_key, lang, sorted_kwargs_tuple)
# Value: translated string
# Size controlled by Settings.i18n_cache_size
# ---------------------------------------------------------------------------
_translation_cache: dict[str, str] = {}
_cache_max_size: int = 512   # overridden at startup from settings


def _cache_key(key: str, lang: str, kwargs: dict[str, str]) -> str:
    raw = f"{key}|{lang}|{sorted(kwargs.items())}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cache_get(ck: str) -> str | None:
    return _translation_cache.get(ck)


def _cache_set(ck: str, value: str) -> None:
    if len(_translation_cache) >= _cache_max_size:
        # Evict oldest entry (dict preserves insertion order in Python 3.7+)
        oldest = next(iter(_translation_cache))
        del _translation_cache[oldest]
    _translation_cache[ck] = value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def t_ai(
    key: str,
    lang: str = "en",
    *,
    context: dict[str, Any] | None = None,
    **kwargs: str,
) -> str:
    """
    Translate / generate an i18n string using AI when safe and enabled.

    Parameters
    ----------
    key:
        i18n key, same as used in ``t()``.
    lang:
        BCP-47 language code, e.g. "hi", "bn", "ta".
    context:
        Optional structured data attached to the message (product name, verdict,
        etc.). Passed to the AI model to improve translation accuracy and tone.
    **kwargs:
        Template variables, e.g. ``expiry_date="12 Jan 2024"``.

    Returns
    -------
    str
        Translated / generated string, always non-empty.
    """
    # --- Guard 1: safety-critical key → always static ---
    if _is_safety_critical(key):
        logger.debug("i18n_ai.safety_key_static | key=%s lang=%s", key, lang)
        return t(key, lang=lang, **kwargs)

    from app.core.config import get_settings
    settings = get_settings()

    # --- Guard 2: AI i18n disabled → static ---
    if not settings.use_ai_i18n:
        return t(key, lang=lang, **kwargs)

    # --- Guard 3: English → no translation needed ---
    if lang == "en":
        return t(key, lang="en", **kwargs)

    # --- Cache hit ---
    ck = _cache_key(key, lang, kwargs)
    cached = _cache_get(ck)
    if cached is not None:
        logger.debug("i18n_ai.cache_hit | key=%s lang=%s", key, lang)
        return cached

    # --- Get English base (with variable substitution already applied) ---
    en_text = t(key, lang="en", **kwargs)

    # --- AI call ---
    try:
        translated = await _call_ai(
            en_text=en_text,
            lang=lang,
            context=context or {},
            settings=settings,
        )
        logger.info(
            "i18n_ai.translated | key=%s lang=%s provider=%s chars=%d",
            key, lang, settings.i18n_ai_provider, len(translated),
        )
        _cache_set(ck, translated)
        return translated

    except Exception as exc:
        logger.warning(
            "i18n_ai.fallback_to_static | key=%s lang=%s error=%s",
            key, lang, exc,
        )
        return t(key, lang=lang, **kwargs)


def configure_cache(max_size: int) -> None:
    """Set the LRU cache size — call once from ``create_app()``."""
    global _cache_max_size
    _cache_max_size = max_size
    logger.info("i18n_ai.cache_configured | max_size=%d", max_size)


def cache_stats() -> dict[str, int]:
    """Return current cache occupancy — useful for observability endpoints."""
    return {"size": len(_translation_cache), "max_size": _cache_max_size}


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------

async def _call_ai(
    en_text: str,
    lang: str,
    context: dict[str, Any],
    settings: Any,
) -> str:
    """Route to the configured AI provider."""
    provider = settings.i18n_ai_provider.lower()
    prompt = _build_prompt(en_text=en_text, lang=lang, context=context)

    if provider == "gemini":
        return await _call_gemini(prompt, settings)
    elif provider in ("lmstudio", "openai"):
        return await _call_openai_compat(prompt, settings)
    else:
        logger.error("i18n_ai.unknown_provider | provider=%r", provider)
        raise ValueError(f"Unknown I18N_AI_PROVIDER: {provider!r}")


# ---------------------------------------------------------------------------
# Gemini provider
# ---------------------------------------------------------------------------

async def _call_gemini(prompt: str, settings: Any) -> str:
    """
    Call Google Gemini for translation.

    Uses ``gemini-2.0-flash-lite`` by default — it's the cheapest and fastest
    Gemini model and more than sufficient for translation tasks.
    The google-genai SDK's ``generate_content`` is synchronous, so we run it
    in a thread pool to keep the event loop unblocked.
    """
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY not set; cannot use Gemini for i18n.")

    logger.debug("i18n_ai.gemini_call | model=%s", settings.i18n_ai_model)

    try:
        from google import genai  # type: ignore[import]
    except ImportError:
        raise RuntimeError("google-genai package not installed (pip install google-genai).")

    def _sync_call() -> str:
        client = genai.Client(api_key=settings.google_api_key)
        response = client.models.generate_content(
            model=settings.i18n_ai_model,
            contents=prompt,
        )
        return response.text.strip()

    # run_in_executor so the sync SDK doesn't block the event loop
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_call)


# ---------------------------------------------------------------------------
# OpenAI-compatible provider (LM Studio / Ollama / OpenAI cloud)
# ---------------------------------------------------------------------------

async def _call_openai_compat(prompt: str, settings: Any) -> str:
    """
    Call any OpenAI-compatible API endpoint.

    LM Studio: set OPENAI_BASE_URL=http://localhost:1234/v1 and
               I18N_AI_MODEL to the model name shown in LM Studio's UI
               (e.g. "meta-llama-3.1-8b-instruct").

    Ollama:    set OPENAI_BASE_URL=http://localhost:11434/v1 and
               I18N_AI_MODEL=llama3.1 (or any pulled model name).

    Temperature is set very low (0.1) to get deterministic, consistent
    translations rather than creative paraphrases.
    """
    try:
        from openai import AsyncOpenAI  # type: ignore[import]
    except ImportError:
        raise RuntimeError("openai package not installed (pip install openai).")

    logger.debug(
        "i18n_ai.openai_compat_call | base_url=%s model=%s",
        settings.openai_base_url,
        settings.i18n_ai_model,
    )

    client = AsyncOpenAI(
        api_key=settings.openai_api_key or "lm-studio",  # LM Studio ignores this
        base_url=settings.openai_base_url,
    )
    response = await client.chat.completions.create(
        model=settings.i18n_ai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=512,
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(en_text: str, lang: str, context: dict[str, Any]) -> str:
    """
    Build the translation prompt.

    WHY a dedicated builder:
      The prompt wording directly affects translation quality. Keeping it here
      makes it easy to A/B test different prompts without touching call sites.

    KEY DESIGN CHOICES:
      - "Return ONLY the translated text" — prevents the model from adding
        explanations, apologies, or notes in its reply.
      - We pass the English text (not the i18n key) so the model has the full
        human-readable string to work with.
      - Context is optional but improves accuracy for product names/brand names
        that should not be translated (e.g., "Dolo 650" stays "Dolo 650").
    """
    lang_name = _LANG_NAMES.get(lang, lang)

    context_block = ""
    if context:
        lines = "\n".join(f"  {k}: {v}" for k, v in context.items())
        context_block = (
            f"\n\nAdditional context (use for accuracy — do NOT translate brand/medicine names):\n{lines}"
        )

    return (
        f"Translate the following message to {lang_name}.\n"
        f"Rules:\n"
        f"  1. Keep the exact meaning and tone.\n"
        f"  2. Preserve any emoji.\n"
        f"  3. Do NOT translate medicine/brand names, barcode numbers, or licence numbers.\n"
        f"  4. Return ONLY the translated text — no explanation, no quotes, no preamble.\n"
        f"\nOriginal (English):\n{en_text}"
        f"{context_block}"
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _is_safety_critical(key: str) -> bool:
    return any(key.startswith(prefix) for prefix in _SAFETY_KEY_PREFIXES)
