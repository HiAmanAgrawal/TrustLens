"""Image-to-text extractor with a Gemini-first fail-chain.

Two-tier on purpose, primary first:

  1. **Google Gemini Vision** — when ``GOOGLE_API_KEY`` is set, this is the
     default OCR engine. It handles curved labels, glare, mixed scripts,
     hand-stamped batch / MFG / EXP fields, dense nutrition tables, and
     small print on Indian pharma / grocery packs that Tesseract chokes
     on. Same chain runs for both medicines and grocery items.
  2. **Tesseract (`pytesseract`)** — local fallback. Used whenever Gemini
     is unavailable (no API key, auth failure, rate limit, network error,
     timeout, or empty response). Free, runs locally, fine for clean
     printed text.

The decision lives entirely inside :func:`extract_text` — callers never
have to pick an engine. The returned ``OcrResult.engine`` says which
engine ultimately produced the text; ``OcrResult.status`` says how the
chain unfolded so the API layer can surface a precise note to the
client (e.g. "your Gemini key was rejected; we used local OCR instead").
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from dataclasses import dataclass

from PIL import Image, ImageFilter, ImageOps

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Sanity bar for "do we have meaningful text". Both engines feed into the
# same check so the chain decision stays uniform regardless of who ran.
_MIN_CONFIDENCE = 0.60
_MIN_ALPHANUM_CHARS = 5

# Hard wall-clock for the cloud call so a hung API doesn't pin the
# request. Tuned to be longer than a typical Gemini Flash response (~3-5s)
# but short enough to feel responsive when the API is degraded.
_GEMINI_TIMEOUT_S = 25.0

# Gemini accepts these natively; anything else we coerce to JPEG below.
_GEMINI_MIME_TYPES: dict[str, str] = {
    "JPEG": "image/jpeg",
    "JPG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "HEIC": "image/heic",
    "HEIF": "image/heif",
}

# Prompt is intentionally directive but compact: long checklisty prompts
# cause Gemini to skip fields. We focus on (1) being exhaustive about
# small print, (2) preserving numbers / codes verbatim, and (3) refusing
# any post-processing the model might be tempted to do.
_GEMINI_PROMPT = (
    "You are a precise OCR engine for product packaging "
    "(pharmaceuticals, food, beverages, cosmetics).\n\n"
    "Task: Transcribe ALL visible printed text on the image, exactly as "
    "printed, including small print near edges, around the barcode, and "
    "on stickers / overprints.\n\n"
    "Be especially careful with numbers and codes — copy them character "
    "for character: batch / lot / B.No., MFG / MFD / PKD / EXP / Best "
    "Before dates, MRP, net weight or quantity, FSSAI licence numbers, "
    "GTIN / EAN / UPC, manufacturing licence numbers (e.g. M/600/2012, "
    "ML24F-0043). Preserve units (g, mg, kcal, %, kJ, °C). Capture every "
    "row of the nutrition table and the entire ingredient list, "
    "including text inside parentheses.\n\n"
    "Rules:\n"
    "- Output exactly what is printed. Do not translate, summarise, "
    "paraphrase, fix typos, infer missing text, or add commentary.\n"
    "- Preserve line breaks where the printed layout has them.\n"
    "- Plain text only — no markdown, bullets, or headers.\n"
    "- If a region is unreadable, omit it silently. Do not write "
    "\"[unreadable]\", \"...\", or similar placeholders."
)


@dataclass(frozen=True)
class OcrResult:
    """Outcome of an OCR pass.

    Always present (even on failure) so callers branch on ``status`` /
    ``confidence`` rather than handling exceptions.
    """

    text: str
    engine: str          # "gemini" or "tesseract"
    confidence: float    # 0.0–1.0; Gemini outputs use a heuristic (no API confidence)
    # Free-form code identifying *what happened* during OCR. Mapped to a
    # StatusCode by the pipeline so this module stays HTTP-schema-free.
    # Possible values:
    #   "ok"                    — primary engine produced strong text
    #   "fallback_used"         — primary unavailable / weak; local Tesseract handled it
    #   "low_confidence"        — best result we could produce was weak
    #   "no_text"               — neither engine produced any text
    #   "tesseract_missing"     — only emitted when the cloud also produced text
    #   "fallback_unavailable"  — no GOOGLE_API_KEY and no Tesseract installed
    #   "fallback_auth_failed"  — Gemini rejected the key (text may still come from Tesseract)
    #   "fallback_rate_limited" — Gemini hit a 429 (text may still come from Tesseract)
    #   "fallback_failed"       — other Gemini error (text may still come from Tesseract)
    #   "image_unreadable"      — PIL couldn't open the bytes
    status: str = "ok"


# --- Public API --------------------------------------------------------------


async def extract_text(image_bytes: bytes) -> OcrResult:
    """Run OCR on raw image bytes and return the best result we can produce.

    Strategy:

    1. **Primary**: Google Gemini Vision (when ``GOOGLE_API_KEY`` is set).
       Returns immediately on a strong response.
    2. **Fallback**: local Tesseract. Runs on any Gemini failure or when
       Gemini isn't configured.

    The status field tells callers how the chain unfolded. Actionable
    cloud failures (auth, rate-limit) are always surfaced even when
    Tesseract saved the day, so the client can prompt the operator to
    fix the configuration.
    """
    settings = get_settings()

    # --- Primary: Gemini ----------------------------------------------------
    primary_failure: str | None = None  # set when Gemini was tried and failed
    if settings.google_api_key:
        try:
            gemini = await asyncio.wait_for(
                _run_gemini(
                    image_bytes,
                    settings.google_api_key,
                    settings.google_vision_model,
                ),
                timeout=_GEMINI_TIMEOUT_S,
            )
            if _is_strong(gemini):
                return _replace_status(gemini, "ok")
            # Empty / thin response. Fall through to Tesseract — the
            # local engine sometimes catches packs Gemini blanks on.
            primary_failure = "fallback_failed"
            logger.info(
                "Gemini returned thin text (%d chars); trying Tesseract.",
                len(gemini.text),
            )
        except asyncio.TimeoutError:
            primary_failure = "fallback_failed"
            logger.warning("Gemini OCR timed out after %.1fs.", _GEMINI_TIMEOUT_S)
        except Exception as exc:
            primary_failure = _classify_gemini_error(exc)
            logger.warning("Gemini OCR failed (%s); trying Tesseract.", primary_failure)

    # --- Fallback: Tesseract ------------------------------------------------
    tesseract = _run_tesseract(image_bytes)

    # PIL couldn't open the bytes — neither engine can recover from that.
    if tesseract.status == "image_unreadable":
        return tesseract

    if _is_strong(tesseract):
        # Surface actionable cloud failures even when local saved us, so
        # the operator knows to fix their key / wait on the rate limit.
        if primary_failure in ("fallback_auth_failed", "fallback_rate_limited"):
            return _replace_status(tesseract, primary_failure)
        # Cloud was simply unavailable (no key) or transient — info note.
        return _replace_status(tesseract, "fallback_used")

    # --- Both engines failed to produce strong text -------------------------
    if tesseract.status == "tesseract_missing":
        if primary_failure:
            # Both the cloud and local engines are unavailable to us.
            return _replace_status(tesseract, primary_failure)
        # No cloud key + no Tesseract = worst case for this deployment.
        return _replace_status(tesseract, "fallback_unavailable")

    # Tesseract ran but the best it could do was empty / low_confidence.
    # If the cloud failed in any way, prefer that signal — it explains
    # why we didn't get the better engine's output.
    if primary_failure:
        return _replace_status(tesseract, primary_failure)
    return tesseract  # carries "no_text" or "low_confidence"


# --- Helpers -----------------------------------------------------------------


def _replace_status(result: OcrResult, status: str) -> OcrResult:
    """Return a copy of ``result`` with ``status`` overridden (frozen dataclass)."""
    return OcrResult(
        text=result.text, engine=result.engine, confidence=result.confidence, status=status
    )


def _classify_gemini_error(exc: BaseException) -> str:
    """Bucket a Gemini exception into one of our ``OcrResult.status`` codes."""
    msg = str(exc).lower()
    if any(k in msg for k in ("api key not valid", "invalid api key", "401", "403", "permission")):
        return "fallback_auth_failed"
    if any(k in msg for k in ("429", "rate limit", "quota", "resource_exhausted")):
        return "fallback_rate_limited"
    return "fallback_failed"


def _is_strong(result: OcrResult) -> bool:
    """Decide whether an OCR pass is good enough to skip the next engine."""
    alnum = sum(ch.isalnum() for ch in result.text)
    return result.confidence >= _MIN_CONFIDENCE and alnum >= _MIN_ALPHANUM_CHARS


def _detect_mime_type(image_bytes: bytes) -> str:
    """Best-effort MIME-type detection so Gemini gets the right Content-Type.

    Falls back to ``image/jpeg`` on any failure — Gemini is tolerant of
    the wrong type as long as the bytes themselves are a recognised
    image, but a correct hint avoids edge-case rejections (especially
    for HEIC photos taken on iPhones).
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            fmt = (image.format or "").upper()
    except Exception:
        return "image/jpeg"
    return _GEMINI_MIME_TYPES.get(fmt, "image/jpeg")


def _preprocess(image_bytes: bytes) -> Image.Image:
    """Common phone-photo cleanup for Tesseract: grayscale, autocontrast, sharpen.

    Adaptive thresholding helped on some packs but hurt on others —
    keeping the pipeline conservative until we have measured ground
    truth. Gemini does NOT need this; it works better on the raw bytes.
    """
    image = Image.open(io.BytesIO(image_bytes))
    grey = ImageOps.autocontrast(image.convert("L"))
    return grey.filter(ImageFilter.SHARPEN)


def _run_tesseract(image_bytes: bytes) -> OcrResult:
    """Sync Tesseract call. Cheap enough to run inline (no thread offload)."""
    try:
        image = _preprocess(image_bytes)
    except Exception:
        logger.exception("PIL failed to open image; returning empty OCR result.")
        return OcrResult(text="", engine="tesseract", confidence=0.0, status="image_unreadable")

    # Lazy import: lets the rest of the OCR module load even when pytesseract
    # isn't installed (the chain still has the Gemini primary to lean on).
    try:
        import pytesseract
    except ImportError:
        logger.warning("pytesseract not installed; relying on the Gemini primary.")
        return OcrResult(text="", engine="tesseract", confidence=0.0, status="tesseract_missing")

    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractNotFoundError:
        logger.error(
            "Tesseract binary not found. Install it (brew install tesseract) "
            "or rely on the Gemini primary."
        )
        return OcrResult(text="", engine="tesseract", confidence=0.0, status="tesseract_missing")

    # Tesseract reports per-word confidence as a string '-1' for non-words and
    # '0'-'100' otherwise. Average only the meaningful entries.
    words: list[str] = []
    confidences: list[float] = []
    for word, conf in zip(data.get("text", []), data.get("conf", []), strict=False):
        word = (word or "").strip()
        if not word:
            continue
        try:
            conf_int = int(float(conf))
        except (TypeError, ValueError):
            continue
        if conf_int < 0:
            continue
        words.append(word)
        confidences.append(conf_int / 100.0)

    text = " ".join(words)
    confidence = sum(confidences) / len(confidences) if confidences else 0.0

    if not text:
        status = "no_text"
    elif confidence < _MIN_CONFIDENCE:
        status = "low_confidence"
    else:
        status = "ok"

    return OcrResult(text=text, engine="tesseract", confidence=confidence, status=status)


async def _run_gemini(image_bytes: bytes, api_key: str, model: str) -> OcrResult:
    """Call Google's Gemini vision model and return its transcription.

    Imported lazily so the module still loads in environments without
    the google-genai package (e.g. CI machines that only run the
    grocery / matcher unit tests).
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    mime_type = _detect_mime_type(image_bytes)
    response = await client.aio.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            _GEMINI_PROMPT,
        ],
    )
    text = (response.text or "").strip()
    # The API doesn't return a confidence score. Use a tiny heuristic so
    # downstream code can still differentiate "obviously something" from
    # "blank". The threshold mirrors ``_MIN_ALPHANUM_CHARS``.
    heuristic_conf = 0.9 if len(re.sub(r"\s+", "", text)) >= _MIN_ALPHANUM_CHARS else 0.2
    return OcrResult(text=text, engine="gemini", confidence=heuristic_conf)
