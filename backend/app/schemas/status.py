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
    # Chain is Gemini-first, Tesseract-fallback. The "fallback" in the names
    # below refers to Tesseract: it is the engine that runs when the cloud
    # primary is unavailable or fails.
    OCR_OK = "ocr_ok"
    OCR_LOW_CONFIDENCE = "ocr_low_confidence"
    OCR_NO_TEXT = "ocr_no_text"
    OCR_TESSERACT_MISSING = "ocr_tesseract_missing"
    OCR_FALLBACK_USED = "ocr_fallback_used"      # local Tesseract was used (cloud unavailable)
    OCR_FALLBACK_UNAVAILABLE = "ocr_fallback_unavailable"  # neither cloud nor local available
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

    # ---- Category routing -------------------------------------------------
    # Surfaced as a Note so the client can show "we treated this as a
    # grocery item" without parsing the verdict shape.
    CATEGORY_PHARMA = "category_pharma"
    CATEGORY_GROCERY = "category_grocery"
    CATEGORY_UNKNOWN = "category_unknown"

    # ---- Grocery: dates ---------------------------------------------------
    EXPIRED = "expired"
    EXPIRES_SOON = "expires_soon"                # < 30 days
    MFG_DATE_MISSING = "mfg_date_missing"
    MFG_OLD_LONG_SHELF_LIFE = "mfg_old_long_shelf_life"

    # ---- Grocery: ingredients --------------------------------------------
    HIDDEN_SUGARS_FOUND = "hidden_sugars_found"
    CONCERNING_E_CODES = "concerning_e_codes"
    MANY_INGREDIENTS = "many_ingredients"        # > 10 distinct items
    ALLERGEN_DECLARATION_FOUND = "allergen_declaration_found"
    ALLERGEN_DECLARATION_MISSING = "allergen_declaration_missing"

    # ---- Grocery: nutrition ----------------------------------------------
    HIGH_SODIUM = "high_sodium"
    TRANS_FAT_PRESENT = "trans_fat_present"
    HIGH_SUGAR = "high_sugar"
    HIGH_SAT_FAT = "high_sat_fat"
    HIGH_TOTAL_FAT = "high_total_fat"            # > 17.5 g per 100 g (FSAI "high")
    PER_SERVING_ONLY = "per_serving_only"        # nutrition table only per-serving
    NUTRITION_TABLE_MISSING = "nutrition_table_missing"
    NUTRITION_TABLE_PARTIAL = "nutrition_table_partial"  # header / hints found, no values parsed

    # ---- Grocery: marketing claims ---------------------------------------
    VAGUE_CLAIM_NATURAL = "vague_claim_natural"
    VAGUE_CLAIM_NO_PRESERVATIVES = "vague_claim_no_preservatives"
    VAGUE_CLAIM_LOW_FAT = "vague_claim_low_fat"
    MULTIGRAIN_NOT_WHOLE = "multigrain_not_whole"

    # ---- Grocery: FSSAI license ------------------------------------------
    FSSAI_VALID = "fssai_valid"
    FSSAI_FORMAT_INVALID = "fssai_format_invalid"
    FSSAI_NOT_FOUND_ON_LABEL = "fssai_not_found_on_label"
    FSSAI_LOOKUP_FAILED = "fssai_lookup_failed"  # online check degraded
    FSSAI_LICENSE_EXPIRED = "fssai_license_expired"


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
        "Local OCR (Tesseract) is not installed; relying on cloud OCR only."
    ),
    StatusCode.OCR_FALLBACK_USED: (
        "Used local OCR (Tesseract) — cloud OCR (Gemini) was unavailable for this request."
    ),
    StatusCode.OCR_FALLBACK_UNAVAILABLE: (
        "No OCR engine available — set GOOGLE_API_KEY (cloud) or install Tesseract (local) "
        "to extract text from images."
    ),
    StatusCode.OCR_FALLBACK_AUTH_FAILED: (
        "The cloud OCR API key was rejected — falling back to local OCR. "
        "Please update GOOGLE_API_KEY for higher-quality results."
    ),
    StatusCode.OCR_FALLBACK_RATE_LIMITED: (
        "Cloud OCR rate limit reached — falling back to local OCR. "
        "Retry in a moment for the best quality on tricky labels."
    ),
    StatusCode.OCR_FALLBACK_FAILED: (
        "Cloud OCR call failed — falling back to local OCR."
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

    StatusCode.CATEGORY_PHARMA: "Treated as a pharmaceutical product.",
    StatusCode.CATEGORY_GROCERY: "Treated as a grocery / packaged food item.",
    StatusCode.CATEGORY_UNKNOWN: (
        "Couldn't tell whether this is a pharma or grocery item; ran best-effort checks."
    ),

    StatusCode.EXPIRED: "This product has passed its expiry date — do not consume.",
    StatusCode.EXPIRES_SOON: "This product expires within the next 30 days.",
    StatusCode.MFG_DATE_MISSING: (
        "No manufacturing date was readable on the label; we couldn't assess freshness."
    ),
    StatusCode.MFG_OLD_LONG_SHELF_LIFE: (
        "This product was manufactured a while ago and has a long shelf life — "
        "common with preservative-heavy items."
    ),

    StatusCode.HIDDEN_SUGARS_FOUND: (
        "Multiple sugar variants found in the ingredients (e.g. maltose, dextrose, "
        "corn syrup). Their combined weight may exceed any single named sugar."
    ),
    StatusCode.CONCERNING_E_CODES: (
        "One or more E-codes linked to health concerns were found in the ingredients."
    ),
    StatusCode.MANY_INGREDIENTS: (
        "This product has a long ingredient list — generally a sign of heavy processing."
    ),
    StatusCode.ALLERGEN_DECLARATION_FOUND: "An allergen declaration was found on the label.",
    StatusCode.ALLERGEN_DECLARATION_MISSING: (
        "No 'Contains:' allergen declaration was found — read the full ingredient list "
        "carefully if you have allergies."
    ),

    StatusCode.HIGH_SODIUM: "High sodium content (above 600 mg per 100 g).",
    StatusCode.TRANS_FAT_PRESENT: "Trans fat is present — ideally this should be 0 g.",
    StatusCode.HIGH_SUGAR: "High sugar content (above 22.5 g per 100 g).",
    StatusCode.HIGH_SAT_FAT: "High saturated fat content (above 5 g per 100 g).",
    StatusCode.HIGH_TOTAL_FAT: (
        "High total fat content (above 17.5 g per 100 g)."
    ),
    StatusCode.PER_SERVING_ONLY: (
        "Nutrition values are given only per serving, not per 100 g — "
        "harder to compare against other products."
    ),
    StatusCode.NUTRITION_TABLE_MISSING: (
        "No nutrition information table was readable on the label."
    ),
    StatusCode.NUTRITION_TABLE_PARTIAL: (
        "A nutrition table was detected but its values were unreadable — "
        "check the printed pack directly."
    ),

    StatusCode.VAGUE_CLAIM_NATURAL: (
        "The label uses the word 'natural', which is not legally defined in most "
        "countries — read the ingredient list rather than trusting the claim."
    ),
    StatusCode.VAGUE_CLAIM_NO_PRESERVATIVES: (
        "'No added preservatives' is not a legally-regulated claim. Verify by "
        "checking the ingredients."
    ),
    StatusCode.VAGUE_CLAIM_LOW_FAT: (
        "'Low fat' products often contain extra sugar to compensate — check the "
        "nutrition table."
    ),
    StatusCode.MULTIGRAIN_NOT_WHOLE: (
        "'Multigrain' on the front of the pack does not mean 'whole grain' — check "
        "that 'whole wheat' or 'whole grain' is the first ingredient."
    ),

    StatusCode.FSSAI_VALID: "FSSAI license number is present and validly formatted.",
    StatusCode.FSSAI_FORMAT_INVALID: (
        "The FSSAI license number on the label is not a valid 14-digit format."
    ),
    StatusCode.FSSAI_NOT_FOUND_ON_LABEL: (
        "No FSSAI license number was found on the label — required by Indian law "
        "for packaged food."
    ),
    StatusCode.FSSAI_LOOKUP_FAILED: (
        "We couldn't verify the FSSAI license online right now. Use the verify URL "
        "in the response to check it manually."
    ),
    StatusCode.FSSAI_LICENSE_EXPIRED: (
        "The FSSAI license on this label has expired according to the FSSAI portal."
    ),
}


# Default severity per code. Used when the producer doesn't specify one.
_DEFAULT_SEVERITY: dict[StatusCode, Severity] = {
    StatusCode.OK: "info",
    StatusCode.OCR_OK: "info",
    StatusCode.OCR_FALLBACK_USED: "info",  # local OCR ran transparently — nothing to do
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
    StatusCode.OCR_TESSERACT_MISSING: "info",  # cloud is the primary; local is optional
    StatusCode.OCR_FALLBACK_UNAVAILABLE: "error",  # no OCR engine at all = blocking
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

    StatusCode.CATEGORY_PHARMA: "info",
    StatusCode.CATEGORY_GROCERY: "info",
    StatusCode.CATEGORY_UNKNOWN: "info",

    StatusCode.EXPIRED: "error",
    StatusCode.EXPIRES_SOON: "warning",
    StatusCode.MFG_DATE_MISSING: "warning",
    StatusCode.MFG_OLD_LONG_SHELF_LIFE: "info",

    StatusCode.HIDDEN_SUGARS_FOUND: "warning",
    StatusCode.CONCERNING_E_CODES: "warning",
    StatusCode.MANY_INGREDIENTS: "info",
    StatusCode.ALLERGEN_DECLARATION_FOUND: "info",
    StatusCode.ALLERGEN_DECLARATION_MISSING: "info",

    StatusCode.HIGH_SODIUM: "warning",
    StatusCode.TRANS_FAT_PRESENT: "warning",
    StatusCode.HIGH_SUGAR: "warning",
    StatusCode.HIGH_SAT_FAT: "warning",
    StatusCode.HIGH_TOTAL_FAT: "warning",
    StatusCode.PER_SERVING_ONLY: "warning",
    StatusCode.NUTRITION_TABLE_MISSING: "info",
    StatusCode.NUTRITION_TABLE_PARTIAL: "warning",

    StatusCode.VAGUE_CLAIM_NATURAL: "info",
    StatusCode.VAGUE_CLAIM_NO_PRESERVATIVES: "info",
    StatusCode.VAGUE_CLAIM_LOW_FAT: "info",
    StatusCode.MULTIGRAIN_NOT_WHOLE: "info",

    StatusCode.FSSAI_VALID: "info",
    StatusCode.FSSAI_FORMAT_INVALID: "warning",
    StatusCode.FSSAI_NOT_FOUND_ON_LABEL: "warning",
    StatusCode.FSSAI_LOOKUP_FAILED: "warning",
    StatusCode.FSSAI_LICENSE_EXPIRED: "error",
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
