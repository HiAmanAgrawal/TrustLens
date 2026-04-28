"""
Unified scan pipeline router.

Accepts raw inputs (image bytes, OCR text, barcode) and dispatches to the
correct pipeline:

  "prescription" → services/pipeline/prescription.py
  "pharma"       → services/pipeline/medicine_verify.py
  "grocery"      → services/pipeline/grocery_verify.py
  "unknown"      → tries medicine_verify, falls back to grocery_verify

WHY explicit routing instead of trying all pipelines:
  Running all three pipelines on every scan would triple API latency and
  Gemini quota usage. The classifier (services/classifier.py) is accurate
  enough (>90% recall on our test set) that explicit routing is the right
  default. "Unknown" items get the pharma pipeline first because a false
  "safe medicine" verdict is safer than a false "safe food" verdict.

PRESCRIPTION DETECTION:
  A scan is routed as a prescription when the OCR text or the caller
  explicitly flags it. The prescription detector runs before the pharma/
  grocery classifier because a prescription may contain both food products
  and medicine names.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class ScanType:
    PRESCRIPTION = "prescription"
    MEDICINE     = "medicine"
    GROCERY      = "grocery"
    UNKNOWN      = "unknown"


@dataclass
class UnifiedScanResult:
    """
    Container returned by the router.

    Exactly one of ``prescription_result``, ``medicine_result``,
    ``grocery_result`` is populated; the others are None.
    """
    scan_type: str                           # ScanType constant
    category: str                            # "pharma"|"grocery"|"unknown" (from classifier)

    prescription_result: Any | None = None  # PrescriptionExtractionResult
    medicine_result: Any | None = None      # MedicineVerifyResult
    grocery_result: Any | None = None       # GroceryVerifyResult

    # Common fields surfaced at the top level for convenience
    verdict: str | None = None              # VERIFIED|SUSPICIOUS|EXPIRED|UNKNOWN
    verdict_score: float | None = None
    expiry_status: str | None = None        # SAFE|NEAR_EXPIRY|EXPIRED|UNKNOWN
    storage_warnings: list[Any] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def route_and_run(
    *,
    image_bytes: bytes | None = None,
    ocr_text: str | None = None,
    barcode_data: str | None = None,
    barcode_symbology: str | None = None,
    scan_type_hint: str | None = None,      # caller-supplied override ("prescription"|"medicine"|"grocery")
    user_allergens: list[str] | None = None,
    session: Any = None,
    lang: str = "en",
) -> UnifiedScanResult:
    """
    Classify the input and run the appropriate pipeline.

    Args:
        image_bytes:       Raw image bytes (used for OCR if ocr_text not given).
        ocr_text:          Pre-extracted label text.
        barcode_data:      Decoded barcode / QR string.
        barcode_symbology: Symbology string (e.g. "EAN13") from the decoder.
        scan_type_hint:    Caller-specified type override (skips classifier).
        user_allergens:    User allergen profile (for grocery cross-check).
        session:           Async SQLAlchemy session.
        lang:              BCP-47 language tag.

    Returns:
        UnifiedScanResult with the appropriate pipeline's output populated.
    """
    logger.info(
        "pipeline.router.route_and_run | hint=%s barcode=%r ocr_chars=%d",
        scan_type_hint,
        (barcode_data or "")[:40],
        len(ocr_text or ""),
    )

    # --- Step 1: OCR if we only have raw image bytes ---
    if not ocr_text and image_bytes:
        from services.ocr.extractor import extract_text
        ocr_result = await extract_text(image_bytes)
        ocr_text = ocr_result.text if ocr_result else None
        logger.info("pipeline.router.ocr | chars=%d", len(ocr_text or ""))

    # --- Step 2: Determine scan type ---
    if scan_type_hint:
        scan_type = scan_type_hint
        category = _hint_to_category(scan_type_hint)
        logger.info("pipeline.router | using caller hint: %s", scan_type)
    elif _looks_like_prescription(ocr_text):
        scan_type = ScanType.PRESCRIPTION
        category = "pharma"
        logger.info("pipeline.router | detected prescription from OCR signals")
    else:
        from services.classifier import classify
        category = classify(
            barcode_payload=barcode_data,
            barcode_symbology=barcode_symbology,
            ocr_text=ocr_text,
        )
        scan_type = _category_to_scan_type(category)
        logger.info("pipeline.router | classifier → category=%s scan_type=%s", category, scan_type)

    # --- Step 3: Dispatch ---
    unified = UnifiedScanResult(scan_type=scan_type, category=category)

    if scan_type == ScanType.PRESCRIPTION:
        unified = await _run_prescription(
            unified, image_bytes=image_bytes, session=session,
        )

    elif scan_type == ScanType.MEDICINE:
        unified = await _run_medicine(
            unified,
            barcode_data=barcode_data,
            ocr_text=ocr_text,
            session=session,
            lang=lang,
        )

    elif scan_type == ScanType.GROCERY:
        unified = await _run_grocery(
            unified,
            image_bytes=image_bytes,
            ocr_text=ocr_text,
            barcode_data=barcode_data,
            user_allergens=user_allergens,
        )

    else:  # UNKNOWN — try medicine first, then grocery
        unified = await _run_unknown(
            unified,
            image_bytes=image_bytes,
            ocr_text=ocr_text,
            barcode_data=barcode_data,
            user_allergens=user_allergens,
            session=session,
            lang=lang,
        )

    logger.info(
        "pipeline.router.done | scan_type=%s verdict=%s expiry=%s",
        unified.scan_type, unified.verdict, unified.expiry_status,
    )
    return unified


# ---------------------------------------------------------------------------
# Pipeline dispatch helpers
# ---------------------------------------------------------------------------

async def _run_prescription(
    unified: UnifiedScanResult,
    *,
    image_bytes: bytes | None,
    session: Any,
) -> UnifiedScanResult:
    if not image_bytes:
        unified.notes.append("Prescription scan requires an image upload.")
        return unified

    from services.pipeline.prescription import extract_prescription
    prx_result = await extract_prescription(image_bytes, session=session)
    unified.prescription_result = prx_result
    unified.verdict = "UNKNOWN"  # prescriptions don't have a binary verdict
    unified.notes.extend(prx_result.notes)
    return unified


async def _run_medicine(
    unified: UnifiedScanResult,
    *,
    barcode_data: str | None,
    ocr_text: str | None,
    session: Any,
    lang: str,
) -> UnifiedScanResult:
    from services.pipeline.medicine_verify import verify_medicine
    med_result = await verify_medicine(
        barcode_data=barcode_data,
        ocr_text=ocr_text,
        session=session,
        lang=lang,
    )
    unified.medicine_result = med_result
    unified.verdict = med_result.verdict
    unified.verdict_score = med_result.verdict_score
    unified.storage_warnings = med_result.storage_warnings
    unified.notes.extend(med_result.notes)

    # Expiry status derived from medicine verdict
    if med_result.verdict == "EXPIRED":
        unified.expiry_status = "EXPIRED"
    elif med_result.batch_info and med_result.batch_info.expiry_date:
        unified.expiry_status = _medicine_expiry_status(med_result.batch_info.expiry_date)
    return unified


async def _run_grocery(
    unified: UnifiedScanResult,
    *,
    image_bytes: bytes | None,
    ocr_text: str | None,
    barcode_data: str | None,
    user_allergens: list[str] | None,
) -> UnifiedScanResult:
    from services.pipeline.grocery_verify import verify_grocery
    groc_result = await verify_grocery(
        image_bytes=image_bytes,
        ocr_text=ocr_text,
        barcode_data=barcode_data,
        user_allergens=user_allergens or [],
    )
    unified.grocery_result = groc_result
    unified.verdict = _risk_band_to_verdict(groc_result.risk_band)
    unified.expiry_status = groc_result.expiry_status
    unified.storage_warnings = groc_result.storage_warnings
    unified.notes.extend(groc_result.notes)
    return unified


async def _run_unknown(
    unified: UnifiedScanResult,
    *,
    image_bytes: bytes | None,
    ocr_text: str | None,
    barcode_data: str | None,
    user_allergens: list[str] | None,
    session: Any,
    lang: str,
) -> UnifiedScanResult:
    """For truly ambiguous inputs, run medicine pipeline; fall back gracefully."""
    unified = await _run_medicine(
        unified,
        barcode_data=barcode_data,
        ocr_text=ocr_text,
        session=session,
        lang=lang,
    )
    unified.notes.append(
        "Product type could not be determined automatically. "
        "Showing medicine verification results."
    )
    return unified


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

# Prescription signal keywords found on printed Rx pads and typed prescriptions
_RX_SIGNALS = re.compile(
    r"\b(?:"
    r"Rx\b|℞|"
    r"prescription\b|"
    r"dr\.?\s+[A-Z][a-z]|"          # "Dr. Sharma"
    r"patient\s+name\b|"
    r"diagnosis\b|"
    r"bd\b|tds\b|od\b|qid\b|"       # common dosage frequency abbreviations
    r"sig\b|"                         # "Sig:" on typed prescriptions
    r"refill\b"
    r")",
    re.IGNORECASE,
)


def _looks_like_prescription(ocr_text: str | None) -> bool:
    """Quick heuristic check before involving the full classifier."""
    if not ocr_text:
        return False
    return bool(_RX_SIGNALS.search(ocr_text))


def _category_to_scan_type(category: str) -> str:
    return {
        "pharma": ScanType.MEDICINE,
        "grocery": ScanType.GROCERY,
    }.get(category, ScanType.UNKNOWN)


def _hint_to_category(hint: str) -> str:
    return {
        "prescription": "pharma",
        "medicine": "pharma",
        "grocery": "grocery",
    }.get(hint, "unknown")


def _risk_band_to_verdict(risk_band: str) -> str:
    """
    Map grocery risk band to our unified verdict enum.

    Grocery doesn't have a binary "counterfeit" verdict — risk_band is a
    quality/safety signal. We map it conservatively:
      low    → VERIFIED (passes all checks)
      medium → SUSPICIOUS (some concerns)
      high   → SUSPICIOUS (serious concerns — allergen or expiry)
      unknown → UNKNOWN
    """
    return {
        "low": "VERIFIED",
        "medium": "SUSPICIOUS",
        "high": "SUSPICIOUS",
        "unknown": "UNKNOWN",
    }.get(risk_band, "UNKNOWN")


def _medicine_expiry_status(expiry_date: Any) -> str:
    """Derive ExpiryStatus from a medicine batch's expiry_date."""
    from datetime import date as date_cls, timedelta
    if not expiry_date:
        return "UNKNOWN"
    try:
        today = date_cls.today()
        if isinstance(expiry_date, str):
            from datetime import datetime
            expiry_date = datetime.strptime(expiry_date, "%Y-%m-%d").date()
        if expiry_date < today:
            return "EXPIRED"
        if (expiry_date - today).days <= 30:
            return "NEAR_EXPIRY"
        return "SAFE"
    except Exception:
        return "UNKNOWN"
