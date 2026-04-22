"""Image-to-text extractor with a fail-chain.

Two-tier on purpose:
  1. **Tesseract** — free, local, ~50–100ms on a phone-sized image. Handles
     clean printed text well.
  2. **Google ADK Vision (Gemini)** — only fires when Tesseract returns weak
     output. Costs per call but copes with curved labels, glare, mixed
     scripts, and Indian-pharma-pack quirks Tesseract chokes on.

The decision lives entirely inside ``extract_text``: callers never have to
pick an engine.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass

from PIL import Image, ImageFilter, ImageOps

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# When Tesseract is below either bar we escalate to the LLM. Tuned for the
# medicine-pack use case where the label is short but information-dense.
_MIN_CONFIDENCE = 0.60
_MIN_ALPHANUM_CHARS = 5


@dataclass(frozen=True)
class OcrResult:
    text: str
    engine: str          # "tesseract" or "gemini" — useful for debugging quality
    confidence: float    # 0.0–1.0; Gemini outputs use a heuristic since the API doesn't expose one
    # Free-form code identifying *what happened* during OCR. Mapped to a
    # StatusCode by the pipeline so this module stays HTTP-schema-free.
    # Possible values: "ok", "low_confidence", "no_text", "tesseract_missing",
    # "fallback_used", "fallback_unavailable", "fallback_auth_failed",
    # "fallback_rate_limited", "fallback_failed", "image_unreadable".
    status: str = "ok"


async def extract_text(image_bytes: bytes) -> OcrResult:
    """Run OCR on raw image bytes and return the best result we can produce.

    Always returns an ``OcrResult`` (even if both engines fail) so callers can
    branch on ``status`` / ``confidence`` rather than handling exceptions.
    """
    tesseract_result = _run_tesseract(image_bytes)

    if _is_strong(tesseract_result):
        return tesseract_result

    # Tesseract was weak. Try the LLM fallback if it's configured; otherwise
    # honestly return the weak Tesseract output rather than silently lying.
    settings = get_settings()
    if not settings.google_api_key:
        logger.warning(
            "OCR confidence low (%.2f, %d chars) but GOOGLE_API_KEY is unset; "
            "returning Tesseract output as-is.",
            tesseract_result.confidence,
            len(tesseract_result.text),
        )
        return _replace_status(tesseract_result, "fallback_unavailable")

    try:
        gemini = await _run_gemini(
            image_bytes, settings.google_api_key, settings.google_vision_model
        )
        return _replace_status(gemini, "fallback_used")
    except Exception as exc:
        # Categorise the failure so the API can tell the user *why* fallback
        # didn't help. Heuristic on str(exc) because google-genai raises a
        # handful of specific error types we'd otherwise have to import.
        status = _classify_gemini_error(exc)
        logger.warning("Gemini OCR fallback failed (%s); returning Tesseract output.", status)
        return _replace_status(tesseract_result, status)


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
    """Decide whether a Tesseract pass is good enough to skip the LLM."""
    alnum = sum(ch.isalnum() for ch in result.text)
    return result.confidence >= _MIN_CONFIDENCE and alnum >= _MIN_ALPHANUM_CHARS


def _preprocess(image_bytes: bytes) -> Image.Image:
    """Common phone-photo cleanup: grayscale, autocontrast, mild sharpen.

    Adaptive thresholding helped on some packs but hurt on others — keeping
    the pipeline conservative until we have measured ground truth.
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
    # isn't installed (the chain still falls through to the Gemini fallback).
    try:
        import pytesseract
    except ImportError:
        logger.warning("pytesseract not installed; relying on the Gemini fallback.")
        return OcrResult(text="", engine="tesseract", confidence=0.0, status="tesseract_missing")

    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractNotFoundError:
        logger.error(
            "Tesseract binary not found. Install it (brew install tesseract) "
            "or rely on the Gemini fallback."
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

    # Tag the outcome so the pipeline can map it to a status code.
    if not text:
        status = "no_text"
    elif confidence < _MIN_CONFIDENCE:
        status = "low_confidence"
    else:
        status = "ok"

    return OcrResult(text=text, engine="tesseract", confidence=confidence, status=status)


async def _run_gemini(image_bytes: bytes, api_key: str, model: str) -> OcrResult:
    """Call Google's Gemini vision model and return its transcription.

    Imported lazily so the module still loads in environments without the
    google-genai package (e.g. CI machines that only run unit tests).
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    prompt = (
        "Transcribe ALL visible printed text from this product packet. "
        "Preserve line breaks where possible. Do not add commentary, "
        "summaries, or markdown — output only the literal text."
    )
    response = await client.aio.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            prompt,
        ],
    )
    text = (response.text or "").strip()
    # The API doesn't return a confidence score. Use a tiny heuristic so the
    # matcher can still differentiate "obviously something" from "blank".
    heuristic_conf = 0.9 if len(re.sub(r"\s+", "", text)) >= _MIN_ALPHANUM_CHARS else 0.2
    return OcrResult(text=text, engine="gemini", confidence=heuristic_conf)
