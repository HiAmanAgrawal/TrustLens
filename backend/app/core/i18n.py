"""
Lightweight i18n (internationalisation) wrapper for TrustLens.

WHY a custom wrapper instead of a full i18n framework:
  - TrustLens serves a small, predictable set of user-facing strings
    (verdict messages, error messages, WhatsApp reply templates).
  - A full gettext/Babel setup adds ~50 MB of .mo files and build steps.
  - This module loads JSON translation catalogues from app/i18n/ once at
    startup and returns translated strings via a single ``t()`` call.

USAGE:
    from app.core.i18n import t, Language

    # In a WhatsApp reply formatter:
    reply = t("verdict.verified.title", lang="hi")

    # With format variables:
    reply = t("verdict.expired.message", lang="ta", expiry_date="12 Jan 2024")

ADDING A NEW LANGUAGE:
    1. Copy ``app/i18n/en.json`` to ``app/i18n/<code>.json``.
    2. Translate every value (keep keys identical).
    3. Add the code to ``Settings.supported_languages``.
    No code changes needed beyond that.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# Supported language codes — must match file names under app/i18n/
Language = Literal["en", "hi", "ta", "mr"]

_DEFAULT_LANG: Language = "en"

# In-memory catalogue: { "hi": {"key": "value", ...}, ... }
_catalogues: dict[str, dict[str, str]] = {}

_I18N_DIR = Path(__file__).parent.parent / "i18n"


def load_catalogues(languages: list[str] | None = None) -> None:
    """
    Load all JSON translation files from ``app/i18n/`` into memory.

    Called once from ``create_app()`` at startup. Subsequent calls to ``t()``
    are pure dictionary lookups with no I/O.
    """
    langs = languages or ["en", "hi", "ta", "mr"]
    for lang in langs:
        path = _I18N_DIR / f"{lang}.json"
        if not path.exists():
            logger.warning("i18n catalogue not found: %s — falling back to en", path)
            continue
        try:
            _catalogues[lang] = json.loads(path.read_text(encoding="utf-8"))
            logger.info("i18n catalogue loaded: lang=%s keys=%d", lang, len(_catalogues[lang]))
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse i18n catalogue %s: %s", path, exc)


def t(key: str, lang: str = _DEFAULT_LANG, **kwargs: str) -> str:
    """
    Translate ``key`` into ``lang``, substituting any ``{variable}`` placeholders.

    Fallback chain:
      1. Requested language
      2. English
      3. The raw key (so a missing translation never crashes the app)

    Example:
        t("scan.verdict.expired", lang="hi", expiry="12 Jan 2024")
        # → "यह बैच 12 Jan 2024 को समाप्त हो गया है।"
    """
    catalogue = _catalogues.get(lang) or _catalogues.get(_DEFAULT_LANG) or {}
    template = catalogue.get(key)

    if template is None:
        # Fallback to English catalogue
        en_catalogue = _catalogues.get(_DEFAULT_LANG, {})
        template = en_catalogue.get(key)

    if template is None:
        logger.warning("i18n key not found: key=%s lang=%s", key, lang)
        return key   # Return the raw key so the UI always shows *something*

    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError as exc:
            logger.warning(
                "i18n template variable missing: key=%s missing=%s", key, exc
            )
            return template   # Return un-substituted template rather than crashing

    return template


def get_supported_languages() -> list[str]:
    """Return the list of languages for which catalogues are loaded."""
    return list(_catalogues.keys())
