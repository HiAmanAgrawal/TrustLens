"""Unified status codes + human-readable messages.

Every part of the pipeline (barcode decoder, OCR engine, scraper, matcher)
produces a ``Note`` describing what happened. Notes bubble up into the
response so the client sees one coherent picture instead of having to infer
"what went wrong" from missing fields.

Two layers:

* ``StatusCode``: stable, machine-readable identifiers. Frontends switch on
  these. Adding a new value is a non-breaking change; renaming one is not.
* ``MESSAGES``: the canonical English message for each code. UIs are free to
  ignore this and render their own translations keyed off ``StatusCode``.

Severities are deliberately small (``info``, ``warning``, ``error``) — fine
enough to colour-code in a UI, coarse enough that we don't argue about
shades. Anything ``error`` should also be reflected in the verdict label
(usually ``unverifiable``); ``warning`` is "we degraded gracefully";
``info`` is for happy-path detail.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "warning", "error"]


class StatusCode(str, Enum):
    # ---- Happy path -------------------------------------------------------
    OK = "ok"

    # ---- Input validation (HTTP 4xx surface) ------------------------------
    EMPTY_UPLOAD = "empty_upload"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    INVALID_REQUEST = "invalid_request"          # Pydantic / schema validation
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    RATE_LIMITED = "rate_limited"
    INTERNAL_ERROR = "internal_error"

    # ---- Image decoding ---------------------------------------------------
    IMAGE_UNREADABLE = "image_unreadable"        # PIL couldn't open the bytes
    QR_NOT_FOUND = "qr_not_found"                # no barcode/QR detected at all
    QR_DETECTED_UNREADABLE = "qr_detected_unreadable"
    QR_NOT_A_URL = "qr_not_a_url"                # decoded, but not a website to scrape

    # ---- OCR --------------------------------------------------------------
    OCR_OK = "ocr_ok"
    OCR_LOW_CONFIDENCE = "ocr_low_confidence"
    OCR_NO_TEXT = "ocr_no_text"
    OCR_TESSERACT_MISSING = "ocr_tesseract_missing"
    OCR_FALLBACK_USED = "ocr_fallback_used"      # informational: we used Gemini
    OCR_FALLBACK_UNAVAILABLE = "ocr_fallback_unavailable"  # no GOOGLE_API_KEY
    OCR_FALLBACK_AUTH_FAILED = "ocr_fallback_auth_failed"  # 401/403 from Gemini
    OCR_FALLBACK_RATE_LIMITED = "ocr_fallback_rate_limited"  # 429 from Gemini
    OCR_FALLBACK_FAILED = "ocr_fallback_failed"  # other Gemini error

    # ---- Scraper ----------------------------------------------------------
    SCRAPE_OK = "scrape_ok"
    SCRAPE_SKIPPED = "scrape_skipped"            # no URL to follow
    SCRAPE_TIMEOUT = "scrape_timeout"
    SCRAPE_DNS_FAILED = "scrape_dns_failed"
    SCRAPE_HTTP_ERROR = "scrape_http_error"      # 4xx/5xx from target
    SCRAPE_CAPTCHA_BLOCKED = "scrape_captcha_blocked"
    SCRAPE_BROWSER_UNAVAILABLE = "scrape_browser_unavailable"  # Playwright not installed
    SCRAPE_FAILED = "scrape_failed"              # everything else

    # ---- Matching ---------------------------------------------------------
    MATCH_OK = "match_ok"
    MATCH_PARTIAL = "match_partial"
    MATCH_DISAGREES = "match_disagrees"
    MATCH_UNVERIFIABLE = "match_unverifiable"    # one side missing
    # No comparison possible (we have one side only) but the side we *do*
    # have is information-rich. Used by /codes when the user submits a URL,
    # we scrape it successfully, but there's no label OCR to compare to —
    # the page contents are still useful as a read-only "what the
    # manufacturer says about this code" panel.
    INFO_ONLY = "info_only"


# Default English messages. Frontends should treat ``StatusCode`` as the source
# of truth and use these strings only as a fallback / for the API docs.
MESSAGES: dict[StatusCode, str] = {
    StatusCode.OK: "Verification completed.",

    StatusCode.EMPTY_UPLOAD: "The uploaded file was empty.",
    StatusCode.UNSUPPORTED_MEDIA_TYPE: (
        "Unsupported file type. Please upload a JPEG, PNG, or WebP image."
    ),
    StatusCode.PAYLOAD_TOO_LARGE: "The uploaded file is larger than the 10 MB limit.",
    StatusCode.INVALID_REQUEST: "The request body did not match the expected shape.",
    StatusCode.UNAUTHORIZED: "Authentication is required.",
    StatusCode.FORBIDDEN: "You do not have permission to access this resource.",
    StatusCode.NOT_FOUND: "The requested resource was not found.",
    StatusCode.METHOD_NOT_ALLOWED: "This HTTP method is not supported on this endpoint.",
    StatusCode.RATE_LIMITED: "Too many requests. Please wait a moment and try again.",
    StatusCode.INTERNAL_ERROR: (
        "Something went wrong on our side. Please try again in a moment."
    ),

    StatusCode.IMAGE_UNREADABLE: (
        "We couldn't open that image. Please re-upload a JPEG, PNG, or WebP file."
    ),
    StatusCode.QR_NOT_FOUND: (
        "No barcode or QR code was detected in the photo. Make sure the code is in "
        "frame, well-lit, and reasonably flat."
    ),
    StatusCode.QR_DETECTED_UNREADABLE: (
        "We spotted a QR code on the pack but couldn't read it — it may be warped, "
        "partially clipped, or out of focus. Please retake the photo holding the "
        "camera flat and closer to the QR."
    ),
    StatusCode.QR_NOT_A_URL: (
        "The code was decoded but doesn't link to a manufacturer website, so we "
        "couldn't cross-check it online."
    ),

    StatusCode.OCR_OK: "Text extracted from the label.",
    StatusCode.OCR_LOW_CONFIDENCE: (
        "The label text was difficult to read. Results may be incomplete."
    ),
    StatusCode.OCR_NO_TEXT: "We couldn't read any text from the image.",
    StatusCode.OCR_TESSERACT_MISSING: (
        "Local OCR (Tesseract) is not installed; using the cloud fallback instead."
    ),
    StatusCode.OCR_FALLBACK_USED: "Used cloud OCR fallback because the local pass was weak.",
    StatusCode.OCR_FALLBACK_UNAVAILABLE: (
        "Cloud OCR fallback is not configured (missing API key); kept the local result."
    ),
    StatusCode.OCR_FALLBACK_AUTH_FAILED: (
        "The cloud OCR API key was rejected. Please check the GOOGLE_API_KEY setting."
    ),
    StatusCode.OCR_FALLBACK_RATE_LIMITED: (
        "Cloud OCR rate limit reached; please retry in a moment."
    ),
    StatusCode.OCR_FALLBACK_FAILED: (
        "Cloud OCR call failed; using the local result instead."
    ),

    StatusCode.SCRAPE_OK: "Manufacturer page fetched.",
    StatusCode.SCRAPE_SKIPPED: (
        "No website to compare against — the code didn't contain a URL."
    ),
    StatusCode.SCRAPE_TIMEOUT: (
        "The manufacturer's website took too long to respond. Please retry."
    ),
    StatusCode.SCRAPE_DNS_FAILED: (
        "We couldn't resolve the website's address. The link may be invalid or offline."
    ),
    StatusCode.SCRAPE_HTTP_ERROR: (
        "The manufacturer's website returned an error response."
    ),
    StatusCode.SCRAPE_CAPTCHA_BLOCKED: (
        "A CAPTCHA stood between us and the page contents. Verification can't be "
        "completed automatically right now."
    ),
    StatusCode.SCRAPE_BROWSER_UNAVAILABLE: (
        "Headless browser is not installed on the server; cannot fetch the page."
    ),
    StatusCode.SCRAPE_FAILED: "We couldn't fetch the manufacturer's website.",

    StatusCode.MATCH_OK: "Label matches the manufacturer's information.",
    StatusCode.MATCH_PARTIAL: (
        "Label and manufacturer information partially match — please double-check."
    ),
    StatusCode.MATCH_DISAGREES: (
        "Label and manufacturer information disagree significantly. Treat with caution."
    ),
    StatusCode.MATCH_UNVERIFIABLE: (
        "We couldn't compare label and source — one of them was missing or unreadable."
    ),
    StatusCode.INFO_ONLY: (
        "Here's what the manufacturer's website says about this code. Compare it "
        "against the printed pack to confirm it matches."
    ),
}


# Default severity per code. Used when the producer doesn't specify one.
_DEFAULT_SEVERITY: dict[StatusCode, Severity] = {
    StatusCode.OK: "info",
    StatusCode.OCR_OK: "info",
    StatusCode.OCR_FALLBACK_USED: "info",
    StatusCode.SCRAPE_OK: "info",
    StatusCode.SCRAPE_SKIPPED: "info",
    StatusCode.MATCH_OK: "info",
    StatusCode.MATCH_PARTIAL: "warning",
    StatusCode.MATCH_DISAGREES: "warning",
    StatusCode.MATCH_UNVERIFIABLE: "warning",
    StatusCode.INFO_ONLY: "info",
    StatusCode.QR_DETECTED_UNREADABLE: "warning",
    StatusCode.QR_NOT_FOUND: "warning",
    StatusCode.QR_NOT_A_URL: "info",
    StatusCode.OCR_LOW_CONFIDENCE: "warning",
    StatusCode.OCR_NO_TEXT: "warning",
    StatusCode.OCR_TESSERACT_MISSING: "warning",
    StatusCode.OCR_FALLBACK_UNAVAILABLE: "warning",
    StatusCode.OCR_FALLBACK_RATE_LIMITED: "warning",
    StatusCode.OCR_FALLBACK_FAILED: "warning",
    StatusCode.SCRAPE_TIMEOUT: "warning",
    StatusCode.SCRAPE_DNS_FAILED: "warning",
    StatusCode.SCRAPE_HTTP_ERROR: "warning",
    StatusCode.SCRAPE_CAPTCHA_BLOCKED: "warning",
    StatusCode.SCRAPE_FAILED: "warning",
    StatusCode.IMAGE_UNREADABLE: "error",
    StatusCode.OCR_FALLBACK_AUTH_FAILED: "error",
    StatusCode.SCRAPE_BROWSER_UNAVAILABLE: "error",
    StatusCode.EMPTY_UPLOAD: "error",
    StatusCode.UNSUPPORTED_MEDIA_TYPE: "error",
    StatusCode.PAYLOAD_TOO_LARGE: "error",
    StatusCode.INVALID_REQUEST: "error",
    StatusCode.UNAUTHORIZED: "error",
    StatusCode.FORBIDDEN: "error",
    StatusCode.NOT_FOUND: "error",
    StatusCode.METHOD_NOT_ALLOWED: "error",
    StatusCode.RATE_LIMITED: "warning",
    StatusCode.INTERNAL_ERROR: "error",
}


class Note(BaseModel):
    """One thing the pipeline wants the client to know.

    A response can carry many notes — e.g. "QR detected but unreadable"
    *and* "OCR fallback used". Keep them flat and ordered so the UI can
    render them as a status timeline.
    """

    code: StatusCode
    message: str
    severity: Severity = "info"


def make_note(code: StatusCode, *, message: str | None = None, severity: Severity | None = None) -> Note:
    """Build a ``Note`` with sensible defaults from the catalogue."""
    return Note(
        code=code,
        message=message or MESSAGES[code],
        severity=severity or _DEFAULT_SEVERITY.get(code, "info"),
    )


class ErrorResponse(BaseModel):
    """Wire shape for 4xx / 5xx responses.

    Mirrors the success envelope's ``status`` + ``message`` so clients can
    branch on ``status`` regardless of HTTP code.
    """

    status: StatusCode
    message: str
    detail: str | None = Field(
        default=None,
        description="Machine-friendly extra context (validation errors, traceback id, ...).",
    )
