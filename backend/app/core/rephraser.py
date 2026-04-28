"""
WhatsApp response rephraser — adapts English templates to Hinglish or Hindi.

WHY:
  Most Indian WhatsApp users communicate in Hinglish (Hindi written in Roman
  script mixed with English). Replying in formal English feels cold and
  reduces comprehension. This module detects the user's language style from
  their incoming message and rephrases the outgoing reply to match it.

LANGUAGE MODES:
  "en"       — English only; no rephrasing, returned as-is.
  "hinglish" — Roman-script Hindi + English mix. Detected when ≥2 common
               Hindi words appear in the incoming message. Reply style:
               casual WhatsApp banter, like a knowledgeable friend.
  "hi"       — Devanagari Hindi. Detected when Devanagari characters appear.
               Reply is fully translated to Hindi script.

SAFETY DESIGN:
  Very short strings (< 30 alnum chars) are returned unchanged — these are
  typically status codes or single-word replies where rephrasing could break
  formatting. Medicine names, numbers, batch codes, and emoji are preserved
  exactly by the prompt.

AI PROVIDER PRIORITY:
  1. Gemini (google_api_key) — fastest, best quality for Indian languages.
  2. LM Studio (lm_studio_base_url) — local fallback, any chat model.
  If both are unavailable the original English reply is returned unchanged.

CACHING:
  Rephrased responses are LRU-cached by (lang, response_prefix_hash) so
  identical template strings are rephrased only once per process restart.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

# Devanagari Unicode block U+0900–U+097F
_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")

# Common Hindi words written in Roman script (Hinglish indicators)
_HINGLISH_WORDS: frozenset[str] = frozenset([
    "kya", "kyaa", "hai", "hain", "nahi", "nahin", "nai", "aur", "ek",
    "yeh", "ye", "yeh", "woh", "wo", "bhai", "yaar", "dost", "bolo",
    "batao", "bata", "acha", "accha", "haan", "theek", "thik", "karo",
    "kar", "lao", "isko", "usko", "inhe", "jyada", "bahut", "thoda",
    "sahi", "galat", "mera", "meri", "mujhe", "kaise", "kaisa", "kyun",
    "kyunki", "toh", "par", "lekin", "ab", "aaj", "kal", "kab", "kahan",
    "kitna", "kitni", "kitne", "chahiye", "chahie", "hoga", "hogi",
    "tha", "thi", "sirf", "sab", "kuch", "koi", "pls", "plz", "bata",
    "dena", "lena", "samajh", "samjha", "dawai", "dawa", "check",
    "safe", "unsafe", "sahi", "galat", "theek", "ठीक", "dekho", "dekh",
    "likh", "padh", "batana", "dikhao", "dikha", "sunao", "suno",
    "chalega", "chale", "aajao", "aao", "jao", "ruko", "ruk",
])

# Need ≥ this many Hinglish word matches to trigger rephrasing
_HINGLISH_THRESHOLD = 2

# Skip rephrasing for very short / emoji-only responses
_MIN_ALNUM_CHARS = 30


def detect_user_language(text: str) -> str:
    """Detect whether a message is Hindi (Devanagari), Hinglish, or English.

    Returns one of: "hi", "hinglish", "en"
    """
    if not text:
        return "en"
    if _DEVANAGARI_RE.search(text):
        return "hi"
    words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
    matches = sum(1 for w in words if w in _HINGLISH_WORDS)
    if matches >= _HINGLISH_THRESHOLD:
        return "hinglish"
    return "en"


# ---------------------------------------------------------------------------
# In-process LRU cache
# ---------------------------------------------------------------------------

_cache: dict[str, str] = {}
_CACHE_MAX = 256


def _cache_key(response: str, lang: str) -> str:
    raw = f"{lang}|{response[:200]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def rephrase(
    response: str,
    lang: str,
    *,
    user_message: str = "",
) -> str:
    """Rephrase an English WhatsApp reply to match the user's language style.

    Parameters
    ----------
    response:
        English reply text to rephrase.
    lang:
        "hi" | "hinglish" | "en". Obtained from detect_user_language().
    user_message:
        The user's original incoming message (used for tone calibration).

    Returns
    -------
    str
        Rephrased text, or the original if rephrasing fails / lang == "en".
    """
    if lang == "en":
        return response

    # Skip very short / non-textual responses
    if sum(c.isalnum() for c in response) < _MIN_ALNUM_CHARS:
        return response

    ck = _cache_key(response, lang)
    if ck in _cache:
        logger.debug("rephraser.cache_hit | lang=%s", lang)
        return _cache[ck]

    try:
        rephrased = await asyncio.wait_for(
            _call_ai(response, lang, user_message=user_message),
            timeout=12.0,
        )
        if rephrased and len(rephrased) > 5:
            if len(_cache) >= _CACHE_MAX:
                del _cache[next(iter(_cache))]
            _cache[ck] = rephrased
            logger.info(
                "rephraser.done | lang=%s in=%d out=%d",
                lang, len(response), len(rephrased),
            )
            return rephrased
    except asyncio.TimeoutError:
        logger.warning("rephraser.timeout | lang=%s — returning English", lang)
    except Exception as exc:
        logger.warning("rephraser.failed | lang=%s error=%s — returning English", lang, exc)

    return response


def clear_cache() -> None:
    _cache.clear()


# ---------------------------------------------------------------------------
# AI provider dispatch
# ---------------------------------------------------------------------------

async def _call_ai(response: str, lang: str, *, user_message: str = "") -> str:
    from app.core.config import get_settings
    s = get_settings()
    prompt = _build_prompt(response, lang, user_message=user_message)

    if s.google_api_key:
        return await _call_gemini(prompt, s)

    if await _lm_studio_available(s):
        return await _call_lm_studio(prompt, s)

    raise RuntimeError("No AI provider configured for rephrasing.")


async def _call_gemini(prompt: str, settings: Any) -> str:
    from google import genai
    client = genai.Client(api_key=settings.google_api_key)
    response = await client.aio.models.generate_content(
        model=settings.i18n_ai_model,
        contents=[prompt],
    )
    return (response.text or "").strip()


async def _lm_studio_available(settings: Any) -> bool:
    try:
        import urllib.request
        req = urllib.request.Request(f"{settings.lm_studio_base_url}/models", method="GET")
        with urllib.request.urlopen(req, timeout=settings.lm_studio_health_timeout_s) as r:
            return r.status < 500
    except Exception:
        return False


async def _call_lm_studio(prompt: str, settings: Any) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(
        api_key=settings.lm_studio_api_key or "lm-studio",
        base_url=settings.lm_studio_base_url,
    )
    response = await client.chat.completions.create(
        model=settings.lm_studio_chat_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1024,
    )
    return (response.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(response: str, lang: str, *, user_message: str = "") -> str:
    if lang == "hinglish":
        style_desc = (
            "Hinglish — a casual mix of Hindi (Roman script) and English, "
            "exactly how Indians talk on WhatsApp. "
            "Example tone: 'Bhai, yeh medicine safe hai! Batch match ho gaya. "
            "Expiry abhi 3 saal door hai, tension mat lo 😊' "
            "Use common Hinglish phrases like 'bilkul', 'ekdum', 'sahi baat', "
            "'tension mat lo', 'check karo', 'batao', 'haan yaar'. "
            "Keep the reply warm, friendly, and direct."
        )
    else:
        style_desc = (
            "Hindi using Devanagari script. Clear, friendly, and easy to "
            "understand for a general Indian audience."
        )

    user_ctx = (
        f"\nUser's original message (for tone reference): {user_message[:120]}"
        if user_message else ""
    )

    return (
        f"Rephrase the following WhatsApp message in {style_desc}\n\n"
        f"STRICT RULES — follow all of them:\n"
        f"  1. Preserve every emoji exactly where it appears.\n"
        f"  2. Keep *bold* WhatsApp markers (* ... *) intact.\n"
        f"  3. Do NOT translate or modify: medicine names, brand names, "
        f"batch numbers, FSSAI IDs, licence numbers, percentages, dates, "
        f"barcode strings, or any number/code.\n"
        f"  4. Keep the exact same information — do not add or omit anything.\n"
        f"  5. Return ONLY the rephrased message text — no explanation, "
        f"no preamble, no quotes around the output.\n"
        f"{user_ctx}\n\n"
        f"Original message:\n{response}"
    )
