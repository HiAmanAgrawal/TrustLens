"""Tests for the Gemini-first OCR chain in ``services.ocr.extractor``.

The extractor is intentionally framework-agnostic; we drive each branch
by monkeypatching ``_run_gemini`` / ``_run_tesseract`` / ``get_settings``
so the tests don't need a Gemini API key, network access, or a Tesseract
install.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

import pytest

from services.ocr import extractor as ocr_extractor
from services.ocr.extractor import OcrResult


# --- Helpers ------------------------------------------------------------------


class _FakeSettings:
    """Stand-in for ``Settings`` covering the only fields the extractor reads."""

    def __init__(self, *, google_api_key: str | None) -> None:
        self.google_api_key = google_api_key
        self.google_vision_model = "gemini-test-model"


def _patch_settings(monkeypatch: pytest.MonkeyPatch, *, key: str | None) -> None:
    monkeypatch.setattr(ocr_extractor, "get_settings", lambda: _FakeSettings(google_api_key=key))


def _patch_gemini(monkeypatch: pytest.MonkeyPatch, fake: Any) -> None:
    monkeypatch.setattr(ocr_extractor, "_run_gemini", fake)


def _patch_tesseract(monkeypatch: pytest.MonkeyPatch, fake: Any) -> None:
    monkeypatch.setattr(ocr_extractor, "_run_tesseract", fake)


_STRONG_TEXT = "Paracetamol IP 500 mg Batch ABC123"  # ≥ _MIN_ALPHANUM_CHARS, lots of alnum
_WEAK_TEXT = "  ?  "  # < _MIN_ALPHANUM_CHARS alnum


# --- 1. Gemini happy path ----------------------------------------------------


@pytest.mark.asyncio
async def test_extract_returns_gemini_text_on_primary_success(monkeypatch) -> None:
    """When Gemini returns strong text, Tesseract should never run."""
    tesseract_called = False

    async def fake_gemini(_image: bytes, _key: str, _model: str) -> OcrResult:
        return OcrResult(text=_STRONG_TEXT, engine="gemini", confidence=0.9)

    def fake_tesseract(_image: bytes) -> OcrResult:
        nonlocal tesseract_called
        tesseract_called = True
        return OcrResult(text="should-not-run", engine="tesseract", confidence=0.99, status="ok")

    _patch_settings(monkeypatch, key="dummy")
    _patch_gemini(monkeypatch, fake_gemini)
    _patch_tesseract(monkeypatch, fake_tesseract)

    result = await ocr_extractor.extract_text(b"fake-bytes")

    assert result.engine == "gemini"
    assert result.text == _STRONG_TEXT
    assert result.status == "ok"
    assert not tesseract_called, "Tesseract must not run when Gemini already produced strong text"


# --- 2. Gemini auth failure → Tesseract saves the day -----------------------


@pytest.mark.asyncio
async def test_auth_failure_falls_back_and_surfaces_actionable_status(monkeypatch) -> None:
    """A bad API key must be surfaced even when local OCR produced text — the
    operator needs to know to fix the key for higher-quality results."""
    async def fake_gemini(_image: bytes, _key: str, _model: str) -> OcrResult:
        raise RuntimeError("API key not valid. Please pass a valid API key.")

    def fake_tesseract(_image: bytes) -> OcrResult:
        return OcrResult(text=_STRONG_TEXT, engine="tesseract", confidence=0.85, status="ok")

    _patch_settings(monkeypatch, key="bad-key")
    _patch_gemini(monkeypatch, fake_gemini)
    _patch_tesseract(monkeypatch, fake_tesseract)

    result = await ocr_extractor.extract_text(b"fake-bytes")

    assert result.engine == "tesseract"
    assert result.text == _STRONG_TEXT
    assert result.status == "fallback_auth_failed"


# --- 3. Gemini rate-limited → Tesseract takes over --------------------------


@pytest.mark.asyncio
async def test_rate_limit_falls_back_and_surfaces_transient_status(monkeypatch) -> None:
    async def fake_gemini(_image: bytes, _key: str, _model: str) -> OcrResult:
        raise RuntimeError("429 RESOURCE_EXHAUSTED: Quota exceeded")

    def fake_tesseract(_image: bytes) -> OcrResult:
        return OcrResult(text=_STRONG_TEXT, engine="tesseract", confidence=0.85, status="ok")

    _patch_settings(monkeypatch, key="dummy")
    _patch_gemini(monkeypatch, fake_gemini)
    _patch_tesseract(monkeypatch, fake_tesseract)

    result = await ocr_extractor.extract_text(b"fake-bytes")

    assert result.engine == "tesseract"
    assert result.status == "fallback_rate_limited"


# --- 4. Gemini generic failure → Tesseract takes over (info note) -----------


@pytest.mark.asyncio
async def test_generic_gemini_failure_with_strong_local_uses_info_note(monkeypatch) -> None:
    """A transient generic failure on the cloud side, when fully covered by
    local OCR, should surface as the soft ``fallback_used`` info — there's
    nothing the operator needs to do about it."""
    async def fake_gemini(_image: bytes, _key: str, _model: str) -> OcrResult:
        raise RuntimeError("Connection reset by peer")

    def fake_tesseract(_image: bytes) -> OcrResult:
        return OcrResult(text=_STRONG_TEXT, engine="tesseract", confidence=0.85, status="ok")

    _patch_settings(monkeypatch, key="dummy")
    _patch_gemini(monkeypatch, fake_gemini)
    _patch_tesseract(monkeypatch, fake_tesseract)

    result = await ocr_extractor.extract_text(b"fake-bytes")

    assert result.engine == "tesseract"
    assert result.status == "fallback_used"


# --- 5. Gemini empty / thin response → Tesseract takes over -----------------


@pytest.mark.asyncio
async def test_empty_gemini_response_falls_back(monkeypatch) -> None:
    """If Gemini returns an empty / single-character response, the local
    engine sometimes catches text it missed — try it before giving up."""
    async def fake_gemini(_image: bytes, _key: str, _model: str) -> OcrResult:
        return OcrResult(text="", engine="gemini", confidence=0.2)

    def fake_tesseract(_image: bytes) -> OcrResult:
        return OcrResult(text=_STRONG_TEXT, engine="tesseract", confidence=0.85, status="ok")

    _patch_settings(monkeypatch, key="dummy")
    _patch_gemini(monkeypatch, fake_gemini)
    _patch_tesseract(monkeypatch, fake_tesseract)

    result = await ocr_extractor.extract_text(b"fake-bytes")

    assert result.engine == "tesseract"
    assert result.text == _STRONG_TEXT
    assert result.status == "fallback_used"


# --- 6. Gemini timeout → Tesseract takes over -------------------------------


@pytest.mark.asyncio
async def test_gemini_timeout_falls_back(monkeypatch) -> None:
    """A hung Gemini call must not pin the request — the chain has to give up
    on the cloud and try the local engine."""
    async def slow_gemini(_image: bytes, _key: str, _model: str) -> OcrResult:
        await asyncio.sleep(60)
        return OcrResult(text="never-arrives", engine="gemini", confidence=0.9)

    def fake_tesseract(_image: bytes) -> OcrResult:
        return OcrResult(text=_STRONG_TEXT, engine="tesseract", confidence=0.85, status="ok")

    _patch_settings(monkeypatch, key="dummy")
    _patch_gemini(monkeypatch, slow_gemini)
    _patch_tesseract(monkeypatch, fake_tesseract)

    # Squeeze the timeout so the test stays fast — we're proving the
    # branch logic, not actually waiting 25 seconds.
    monkeypatch.setattr(ocr_extractor, "_GEMINI_TIMEOUT_S", 0.05)

    result = await ocr_extractor.extract_text(b"fake-bytes")

    assert result.engine == "tesseract"
    assert result.status == "fallback_used"


# --- 7. No GOOGLE_API_KEY → straight to Tesseract --------------------------


@pytest.mark.asyncio
async def test_missing_api_key_skips_gemini_and_uses_tesseract(monkeypatch) -> None:
    """When the cloud isn't configured at all, Tesseract should run silently
    (info note only) — this is a normal local-only deployment."""
    gemini_called = False

    async def fake_gemini(_image: bytes, _key: str, _model: str) -> OcrResult:
        nonlocal gemini_called
        gemini_called = True
        return OcrResult(text="should-not-run", engine="gemini", confidence=0.9)

    def fake_tesseract(_image: bytes) -> OcrResult:
        return OcrResult(text=_STRONG_TEXT, engine="tesseract", confidence=0.85, status="ok")

    _patch_settings(monkeypatch, key=None)
    _patch_gemini(monkeypatch, fake_gemini)
    _patch_tesseract(monkeypatch, fake_tesseract)

    result = await ocr_extractor.extract_text(b"fake-bytes")

    assert not gemini_called
    assert result.engine == "tesseract"
    assert result.status == "fallback_used"
    assert result.text == _STRONG_TEXT


# --- 8. Both engines fail --------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_auth_fails_and_tesseract_empty_keeps_actionable_status(
    monkeypatch,
) -> None:
    """Cloud auth failure must remain the surfaced status when the local
    engine also produced nothing — text is empty either way, and the
    operator's job is to fix the key first."""
    async def fake_gemini(_image: bytes, _key: str, _model: str) -> OcrResult:
        raise RuntimeError("Invalid API key, 403")

    def fake_tesseract(_image: bytes) -> OcrResult:
        return OcrResult(text="", engine="tesseract", confidence=0.0, status="no_text")

    _patch_settings(monkeypatch, key="bad")
    _patch_gemini(monkeypatch, fake_gemini)
    _patch_tesseract(monkeypatch, fake_tesseract)

    result = await ocr_extractor.extract_text(b"fake-bytes")

    assert result.text == ""
    assert result.engine == "tesseract"
    assert result.status == "fallback_auth_failed"


@pytest.mark.asyncio
async def test_no_key_and_tesseract_missing_marks_unavailable(monkeypatch) -> None:
    """No cloud + no local = a deployment problem; surface the loudest signal."""
    async def fake_gemini(_image: bytes, _key: str, _model: str) -> OcrResult:
        raise AssertionError("Gemini must not run when there is no key")

    def fake_tesseract(_image: bytes) -> OcrResult:
        return OcrResult(text="", engine="tesseract", confidence=0.0, status="tesseract_missing")

    _patch_settings(monkeypatch, key=None)
    _patch_gemini(monkeypatch, fake_gemini)
    _patch_tesseract(monkeypatch, fake_tesseract)

    result = await ocr_extractor.extract_text(b"fake-bytes")

    assert result.status == "fallback_unavailable"


# --- 9. Image unreadable propagates regardless of cloud outcome -------------


@pytest.mark.asyncio
async def test_image_unreadable_propagates(monkeypatch) -> None:
    """If PIL can't open the bytes Tesseract emits image_unreadable; the
    chain must not paper over that with a cloud-failure code."""
    async def fake_gemini(_image: bytes, _key: str, _model: str) -> OcrResult:
        raise RuntimeError("400 invalid image")

    def fake_tesseract(_image: bytes) -> OcrResult:
        return OcrResult(text="", engine="tesseract", confidence=0.0, status="image_unreadable")

    _patch_settings(monkeypatch, key="dummy")
    _patch_gemini(monkeypatch, fake_gemini)
    _patch_tesseract(monkeypatch, fake_tesseract)

    result = await ocr_extractor.extract_text(b"not-an-image")

    assert result.status == "image_unreadable"


# --- 10. Error classifier behaviour ----------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (RuntimeError("API key not valid"), "fallback_auth_failed"),
        (RuntimeError("HTTP 401 Unauthorized"), "fallback_auth_failed"),
        (RuntimeError("HTTP 403 Forbidden"), "fallback_auth_failed"),
        (RuntimeError("Permission denied for this resource"), "fallback_auth_failed"),
        (RuntimeError("HTTP 429 Too Many Requests"), "fallback_rate_limited"),
        (RuntimeError("RESOURCE_EXHAUSTED: quota"), "fallback_rate_limited"),
        (RuntimeError("Connection reset"), "fallback_failed"),
        (ValueError("Unexpected response"), "fallback_failed"),
    ],
)
def test_classify_gemini_error_buckets(exc: BaseException, expected: str) -> None:
    assert ocr_extractor._classify_gemini_error(exc) == expected


# --- 11. _is_strong threshold -----------------------------------------------


def test_is_strong_requires_confidence_and_alnum_chars() -> None:
    weak_conf = OcrResult(text=_STRONG_TEXT, engine="gemini", confidence=0.3)
    weak_text = OcrResult(text=_WEAK_TEXT, engine="gemini", confidence=0.95)
    strong = OcrResult(text=_STRONG_TEXT, engine="gemini", confidence=0.9)

    assert not ocr_extractor._is_strong(weak_conf)
    assert not ocr_extractor._is_strong(weak_text)
    assert ocr_extractor._is_strong(strong)


# --- 12. Result dataclass is immutable / sane ------------------------------


def test_ocr_result_is_frozen() -> None:
    """``replace`` from dataclasses must be the only way to mutate the result."""
    result = OcrResult(text="hi", engine="gemini", confidence=0.9)
    with pytest.raises(Exception):
        result.text = "tampered"  # type: ignore[misc]

    updated = replace(result, status="fallback_used")
    assert updated.status == "fallback_used"
    assert result.status == "ok"
