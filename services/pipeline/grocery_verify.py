"""
Grocery verification pipeline — Phase 3.

Wraps the existing services/grocery/analyzer.py and adds:
  1. Tavily-backed FSSAI verification fallback (when Playwright FoSCoS fails).
  2. Structured ExpiryStatus enum (SAFE | NEAR_EXPIRY | EXPIRED | UNKNOWN).
  3. Storage condition extraction from the label.
  4. Allergen cross-check against a caller-supplied user profile.
  5. Risk band augmented with expiry and FSSAI status.

This module owns the "grocery verdict" concept while the underlying modules
own their individual checks. The pipeline becomes:

  image → OCR → grocery/analyzer.analyze() → enhance_with_tavily_fssai()
              → extract_storage_warnings()
              → cross_check_allergens()
              → build GroceryVerifyResult
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .storage import StorageWarning, extract_storage_warnings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class ExpiryStatus:
    SAFE        = "SAFE"           # well within expiry
    NEAR_EXPIRY = "NEAR_EXPIRY"   # < 30 days remaining
    EXPIRED     = "EXPIRED"        # past expiry date
    UNKNOWN     = "UNKNOWN"        # no date found on label


@dataclass
class FssaiVerifyResult:
    """FSSAI verification summary returned to the API consumer."""
    license_number: str | None = None
    format_valid: bool = False
    online_status: str = "skipped"      # valid|invalid|expired|lookup_failed|skipped|tavily_verified
    business_name: str | None = None
    expiry: str | None = None
    verify_url: str = "https://foscos.fssai.gov.in/"
    tavily_used: bool = False
    tavily_snippet: str | None = None   # raw search snippet for transparency


@dataclass
class GroceryVerifyResult:
    """
    Complete grocery verification output.

    risk_band      — low | medium | high | unknown
    expiry_status  — SAFE | NEAR_EXPIRY | EXPIRED | UNKNOWN
    """
    risk_band: str = "unknown"
    expiry_status: str = ExpiryStatus.UNKNOWN

    # Extracted dates from label
    dates: dict[str, str] = field(default_factory=dict)

    # Findings list from the static analyzer (expiry, nutrition, FSSAI, claims)
    findings: list[dict[str, Any]] = field(default_factory=list)

    # FSSAI verification
    fssai: FssaiVerifyResult | None = None

    # Ingredients — count from rule-based extractor, full list from Gemini
    ingredients_count: int | None = None
    ingredients: list[str] = field(default_factory=list)
    allergen_warnings: list[str] = field(default_factory=list)

    # Storage
    storage_warnings: list[StorageWarning] = field(default_factory=list)

    # Rich product extraction (Gemini Vision) — None if extraction failed
    product_extraction: Any | None = None  # services.grocery.gemini_extract.ProductExtraction

    # Pipeline meta
    barcode_data: str | None = None
    ocr_chars: int = 0
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def verify_grocery(
    *,
    image_bytes: bytes | None = None,
    ocr_text: str | None = None,
    barcode_data: str | None = None,
    user_allergens: list[str] | None = None,   # lowercase allergen names from user profile
    now: datetime | None = None,
    session: Any = None,                        # reserved for future DB lookups
) -> GroceryVerifyResult:
    """
    Run the full grocery verification pipeline.

    Args:
        image_bytes:    Raw image bytes (used to OCR if ocr_text is None).
        ocr_text:       Pre-extracted label text (skip OCR if already done).
        barcode_data:   Decoded barcode / QR string.
        user_allergens: List of allergen names from the user's profile (lowercase).
        now:            Override "current time" (for deterministic tests).

    Returns:
        GroceryVerifyResult ready for the API response.
    """
    logger.info(
        "grocery_verify.start | barcode=%r ocr_provided=%s image_provided=%s",
        barcode_data, bool(ocr_text), bool(image_bytes),
    )

    import asyncio

    # --- Step 1: Run OCR + Gemini structured extraction concurrently ---
    ocr_task = None
    gemini_task = None

    if not ocr_text and image_bytes:
        async def _do_ocr() -> str | None:
            from services.ocr.extractor import extract_text
            r = await extract_text(image_bytes)
            return r.text if r else None

        ocr_task = asyncio.create_task(_do_ocr())

    if image_bytes:
        async def _do_gemini() -> Any:
            from services.grocery.gemini_extract import extract_product_info
            return await extract_product_info(image_bytes)

        gemini_task = asyncio.create_task(_do_gemini())

    # Await OCR result first (needed for rule-based analysis)
    if ocr_task is not None:
        ocr_text = await ocr_task
        logger.info("grocery_verify.ocr | chars=%d", len(ocr_text or ""))

    result = GroceryVerifyResult(
        barcode_data=barcode_data,
        ocr_chars=len(ocr_text or ""),
    )

    if not ocr_text or not ocr_text.strip():
        # Even without OCR text, wait for Gemini and use its data
        if gemini_task is not None:
            extraction = await gemini_task
            if extraction and extraction.extraction_method != "failed":
                result.product_extraction = extraction
                result.ingredients = extraction.ingredients
                result.ingredients_count = extraction.ingredients_count
                if extraction.brand_name or extraction.product_name:
                    result.notes.append(
                        f"Label text unreadable by OCR; Gemini extracted product info "
                        f"({extraction.extraction_method})."
                    )
                return result
        result.notes.append("No label text found — could not analyze this product.")
        return result

    # --- Step 2: Static grocery analysis (rule-based) ---
    from services.grocery.analyzer import analyze
    analysis = await analyze(ocr_text, now=now, online_fssai=True)
    logger.info(
        "grocery_verify.analysis | risk=%s findings=%d fssai_status=%s",
        analysis.risk_band,
        len(analysis.findings),
        analysis.fssai.online_status if analysis.fssai else "none",
    )

    result.risk_band = analysis.risk_band
    result.dates = analysis.dates
    result.findings = [f.model_dump() for f in analysis.findings]
    result.ingredients_count = analysis.ingredients_count

    # --- Step 2b: Merge Gemini Vision extraction ---
    if gemini_task is not None:
        try:
            extraction = await gemini_task
        except Exception as exc:
            logger.warning("grocery_verify.gemini_task | failed: %s", exc)
            extraction = None

        if extraction and extraction.extraction_method != "failed":
            result.product_extraction = extraction
            result.ingredients = extraction.ingredients

            # Fill in count when rule-based extractor returned None (most common case)
            if result.ingredients_count is None and extraction.ingredients_count:
                result.ingredients_count = extraction.ingredients_count
                logger.info(
                    "grocery_verify.merge | ingredients_count filled from gemini: %d",
                    result.ingredients_count,
                )

            # Gemini FSSAI license overrides regex extraction when not already found
            if extraction.fssai_license and not (analysis.fssai and analysis.fssai.license_number):
                logger.info(
                    "grocery_verify.merge | FSSAI license from gemini: %s",
                    extraction.fssai_license,
                )
                # Patch ocr_text with the extracted number so _build_fssai_result can use it
                ocr_text = ocr_text + f"\nFSSAI Lic No: {extraction.fssai_license}"

            logger.info(
                "grocery_verify.merge | method=%s brand=%r positives=%d negatives=%d",
                extraction.extraction_method,
                extraction.brand_name,
                len(extraction.positives),
                len(extraction.negatives),
            )
        else:
            logger.warning("grocery_verify.merge | gemini extraction failed or unavailable")

    # --- Step 3: Expiry status (structured enum from dates findings) ---
    result.expiry_status = _derive_expiry_status(analysis)

    # --- Step 4: FSSAI — enhance with Tavily fallback if online check failed ---
    result.fssai = await _build_fssai_result(analysis.fssai, ocr_text)

    # Bump risk band if FSSAI license is invalid/expired
    if result.fssai and result.fssai.online_status in ("invalid", "expired"):
        if result.risk_band == "low":
            result.risk_band = "medium"
        result.notes.append(
            f"FSSAI license {result.fssai.license_number} "
            f"appears {result.fssai.online_status} — verify before purchase."
        )

    # --- Step 5: Allergen cross-check ---
    if user_allergens:
        result.allergen_warnings = _cross_check_allergens(ocr_text, user_allergens)
        if result.allergen_warnings:
            result.risk_band = "high"    # allergen always overrides to high risk
            result.notes.append(
                "⚠️ This product may contain allergens from your profile: "
                + ", ".join(result.allergen_warnings)
            )
            logger.warning(
                "grocery_verify.allergens | found=%s", result.allergen_warnings,
            )

    # --- Step 6: Storage warnings ---
    result.storage_warnings = extract_storage_warnings(ocr_text)
    logger.info(
        "grocery_verify.storage | warnings=%d", len(result.storage_warnings),
    )

    logger.info(
        "grocery_verify.done | risk=%s expiry=%s fssai=%s allergens=%d",
        result.risk_band,
        result.expiry_status,
        result.fssai.online_status if result.fssai else "none",
        len(result.allergen_warnings),
    )
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _derive_expiry_status(analysis: Any) -> str:
    """
    Translate findings list into a structured ExpiryStatus.

    The grocery analyzer already has EXPIRED / EXPIRES_SOON status codes as
    findings. We pick the highest-severity one and map to our enum.
    """
    from app.schemas.status import StatusCode

    codes = {f.code for f in analysis.findings}

    if StatusCode.EXPIRED in codes:
        return ExpiryStatus.EXPIRED
    if StatusCode.EXPIRES_SOON in codes:
        return ExpiryStatus.NEAR_EXPIRY

    # If we have at least one parseable date and nothing bad fired → SAFE
    if analysis.dates:
        return ExpiryStatus.SAFE

    return ExpiryStatus.UNKNOWN


async def _build_fssai_result(
    existing_check: Any | None,
    ocr_text: str,
) -> FssaiVerifyResult | None:
    """
    Build a FssaiVerifyResult, using Tavily as fallback when the primary
    Playwright-based FoSCoS lookup has failed.
    """
    from services.grocery.fssai import extract_license, validate_format

    license_number = existing_check.license_number if existing_check else extract_license(ocr_text)

    base = FssaiVerifyResult(
        license_number=license_number,
        format_valid=validate_format(license_number) if license_number else False,
        online_status=existing_check.online_status if existing_check else "skipped",
        business_name=existing_check.business_name if existing_check else None,
        expiry=existing_check.expiry if existing_check else None,
    )

    if not license_number:
        return base

    # Only call Tavily if the Playwright lookup didn't get a clean result
    needs_tavily = base.online_status in ("lookup_failed", "skipped", "unknown")

    if needs_tavily and base.format_valid:
        logger.info(
            "grocery_verify._build_fssai_result | "
            "Playwright status=%s, trying Tavily fallback for license=%s",
            base.online_status, license_number,
        )
        tavily_result = await _tavily_fssai(license_number)
        if tavily_result:
            base.online_status = tavily_result["status"]
            base.business_name = base.business_name or tavily_result.get("business_name")
            base.tavily_used = True
            base.tavily_snippet = tavily_result.get("snippet")
            logger.info(
                "grocery_verify._build_fssai_result | Tavily result status=%s",
                base.online_status,
            )

    return base


async def _tavily_fssai(license_number: str) -> dict | None:
    """
    Use Tavily to infer FSSAI license status from web search results.

    The search results often contain FoSCoS-indexed pages or news articles
    that mention whether a license is valid or has been cancelled/expired.
    We apply keyword heuristics similar to the Playwright-based parser.
    """
    try:
        from services.search.tavily import search_fssai_license

        tavily_result = await search_fssai_license(license_number)
        if tavily_result.status != "ok" or not tavily_result.combined_text:
            return None

        text = tavily_result.combined_text.lower()
        snippet = tavily_result.snippets[0] if tavily_result.snippets else ""

        # Attempt to extract business name near the license number
        business_name = _extract_business_from_snippet(snippet, license_number)

        # Keyword heuristics for status
        if any(t in text for t in ("no record", "invalid", "not found", "not registered")):
            return {"status": "invalid", "snippet": snippet, "business_name": business_name}
        if "expired" in text:
            return {"status": "expired", "snippet": snippet, "business_name": business_name}
        if any(t in text for t in ("valid", "active", "registered", "licensed")):
            return {"status": "valid", "snippet": snippet, "business_name": business_name}

        # Tavily found something but we can't determine status — better than nothing
        return {"status": "unknown", "snippet": snippet, "business_name": business_name}

    except Exception as exc:
        logger.warning("grocery_verify._tavily_fssai | failed: %s", exc)
        return None


def _extract_business_from_snippet(snippet: str, license_number: str) -> str | None:
    """Very rough heuristic: text near the license number is often the business name."""
    import re
    if not snippet:
        return None
    # Look for a capitalized phrase near the license number
    m = re.search(
        r"(?:licensed\s+to|company\s+name|business|firm)[:\s]+([A-Z][A-Za-z\s&.,\-]{5,60})",
        snippet,
        re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def _cross_check_allergens(ocr_text: str, user_allergens: list[str]) -> list[str]:
    """
    Check whether any user allergens appear in the OCR'd label text.

    Simple case-insensitive substring match. The grocery analyzer already
    flags common allergen keywords in the ingredients block — here we also
    check the full text so allergens printed in the "Contains:" section
    (outside the ingredients list) are also caught.
    """
    if not ocr_text or not user_allergens:
        return []

    text_lower = ocr_text.lower()
    triggered = []
    for allergen in user_allergens:
        # Match whole word or whole phrase (no partial matches like "milk" in "milkweed")
        import re
        if re.search(r"\b" + re.escape(allergen.lower()) + r"\b", text_lower):
            triggered.append(allergen)
    return triggered
