"""
Medicine verification pipeline — Phase 3.

Full pipeline for answering "Is this medicine authentic and safe?":

  1. DB identity resolution (Medicine + MedicineBatch by barcode).
  2. Playwright manufacturer-portal scraping (primary source of truth).
  3. Tavily web search fallback when the scraper fails or returns nothing.
  4. Matcher engine comparison (OCR label ↔ scraped/searched text).
  5. Batch expiry check (hard override of matcher verdict).
  6. Storage condition extraction from OCR text.

Returns a ``MedicineVerifyResult`` dataclass — the service layer persists it
as a ``MedicineScanEvent`` row; this module has no DB writes of its own so
it stays reusable outside FastAPI (CLI, tests, WhatsApp handler).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .storage import StorageWarning, extract_storage_warnings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class BatchInfo:
    """Subset of MedicineBatch fields surfaced in the API response."""
    batch_id: str
    batch_number: str | None
    expiry_date: date | None
    manufacture_date: date | None
    is_expired: bool = False


@dataclass
class MedicineVerifyResult:
    """
    Structured output of the medicine verification pipeline.

    ``verdict``      — VERIFIED | SUSPICIOUS | EXPIRED | UNKNOWN
    ``verdict_score``— 0–10 from the matcher; None if matcher had nothing to work with.
    ``source``       — "db+scraper" | "db+tavily" | "db_only" | "matcher_only" | "unknown"
    """
    verdict: str                                    # AuthenticityVerdictEnum value
    verdict_score: float | None = None
    verdict_summary: str = ""
    source: str = "unknown"

    # Product identity (resolved from barcode → DB)
    medicine_id: str | None = None
    batch_id: str | None = None
    brand_name: str | None = None
    generic_name: str | None = None
    manufacturer_name: str | None = None
    batch_info: BatchInfo | None = None

    # Structured fields parsed from OCR text (populated when barcode DB lookup misses)
    extracted_label: dict[str, Any] = field(default_factory=dict)

    # Evidence trail
    scrape_status: str = "skipped"                  # ok|timeout|failed|tavily_fallback|skipped
    tavily_used: bool = False
    matcher_details: dict[str, Any] = field(default_factory=dict)

    # Storage conditions
    storage_warnings: list[StorageWarning] = field(default_factory=list)

    # Pipeline notes (shown in the UI)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def verify_medicine(
    *,
    barcode_data: str | None,
    ocr_text: str | None,
    session: Any,                   # AsyncSession
    lang: str = "en",
) -> MedicineVerifyResult:
    """
    Run the complete medicine verification pipeline for one scan.

    Args:
        barcode_data: Raw decoded barcode / QR string (may be a URL).
        ocr_text:     Text extracted from the label image by OCR.
        session:      Async SQLAlchemy session for DB identity resolution.
        lang:         BCP-47 language code for i18n (unused internally, threaded through).

    Returns:
        ``MedicineVerifyResult`` ready to be persisted by the service layer.
    """
    logger.info(
        "medicine_verify.start | barcode=%r ocr_chars=%d",
        (barcode_data or "")[:60],
        len(ocr_text or ""),
    )

    result = MedicineVerifyResult(verdict="UNKNOWN")

    # --- Step 1: DB identity resolution from barcode ---
    if barcode_data:
        await _resolve_identity(result, barcode_data, session)

    # --- Step 1.5: Structured label extraction from OCR text ---
    # Runs whenever we have OCR text — fills brand/salt/batch/expiry/manufacturer
    # from the label so Tavily and the matcher have real fields to work with even
    # when the barcode isn't in our DB.
    if ocr_text:
        extracted = await _gemini_extract_label(ocr_text)
        result.extracted_label = extracted
        if extracted:
            if not result.brand_name:
                result.brand_name = extracted.get("brand_name")
            if not result.generic_name:
                result.generic_name = extracted.get("generic_name")
            if not result.manufacturer_name:
                result.manufacturer_name = extracted.get("manufacturer")
            # Synthesise a BatchInfo from extracted dates when DB has no batch row
            if not result.batch_info and extracted.get("batch_number"):
                result.batch_info = BatchInfo(
                    batch_id="extracted",
                    batch_number=extracted.get("batch_number"),
                    expiry_date=_parse_ym_date(extracted.get("expiry_date")),
                    manufacture_date=_parse_ym_date(extracted.get("mfg_date")),
                    is_expired=False,
                )
                # Check expiry on the synthesised batch
                if result.batch_info.expiry_date:
                    result.batch_info = BatchInfo(
                        batch_id="extracted",
                        batch_number=result.batch_info.batch_number,
                        expiry_date=result.batch_info.expiry_date,
                        manufacture_date=result.batch_info.manufacture_date,
                        is_expired=result.batch_info.expiry_date < date.today(),
                    )
            logger.info(
                "medicine_verify.label_extraction | brand=%r salt=%r batch=%r exp=%r",
                extracted.get("brand_name"),
                extracted.get("salt"),
                extracted.get("batch_number"),
                extracted.get("expiry_date"),
            )

    # --- Step 2: Scrape manufacturer portal (if barcode is a URL) ---
    scraped_text: str | None = None
    if barcode_data and barcode_data.startswith(("http://", "https://")):
        scraped_text = await _scrape(result, barcode_data)

    # --- Step 3: Tavily fallback when scraper has nothing ---
    if not scraped_text:
        scraped_text = await _tavily_fallback(result, barcode_data, ocr_text)

    # --- Step 4: Matcher comparison ---
    await _run_matcher(result, barcode_data, ocr_text, scraped_text)

    # --- Step 5: Expiry hard-override ---
    if result.batch_info and result.batch_info.is_expired:
        result.verdict = "EXPIRED"
        result.notes.append("Batch expiry date has passed — this product should not be used.")
        logger.info("medicine_verify.expired | batch_id=%s", result.batch_id)

    # --- Step 6: Storage warnings from OCR label ---
    result.storage_warnings = extract_storage_warnings(ocr_text)
    logger.info(
        "medicine_verify.storage | warnings=%d",
        len(result.storage_warnings),
    )

    logger.info(
        "medicine_verify.done | verdict=%s score=%s source=%s",
        result.verdict, result.verdict_score, result.source,
    )
    return result


# ---------------------------------------------------------------------------
# Internal steps
# ---------------------------------------------------------------------------

async def _resolve_identity(
    result: MedicineVerifyResult,
    barcode_data: str,
    session: Any,
) -> None:
    """Look up Medicine + MedicineBatch from the DB using the barcode."""
    try:
        from app.services.medicine_service import find_by_barcode, is_batch_expired
        match = await find_by_barcode(session, barcode_data)
        if not match:
            logger.info("medicine_verify._resolve_identity | barcode not in DB")
            return

        medicine, batch = match
        result.medicine_id = str(medicine.id)
        result.brand_name = medicine.brand_name
        result.generic_name = medicine.generic_name
        result.manufacturer_name = medicine.manufacturer_name
        logger.info(
            "medicine_verify._resolve_identity | medicine=%s brand=%r",
            result.medicine_id, result.brand_name,
        )

        if batch:
            expired = await is_batch_expired(batch)
            result.batch_id = str(batch.id)
            result.batch_info = BatchInfo(
                batch_id=str(batch.id),
                batch_number=batch.batch_number,
                expiry_date=batch.expiry_date,
                manufacture_date=batch.manufacture_date,
                is_expired=expired,
            )
            logger.info(
                "medicine_verify._resolve_identity | batch=%s expired=%s",
                result.batch_id, expired,
            )

    except Exception as exc:
        logger.warning("medicine_verify._resolve_identity | failed: %s", exc)


async def _scrape(result: MedicineVerifyResult, url: str) -> str | None:
    """
    Run the Playwright scraper.

    Returns the visible page text on success; updates result.scrape_status.
    """
    logger.info("medicine_verify._scrape | url=%r", url[:80])
    try:
        from services.scraper.agent import scrape_url
        scrape_result = await scrape_url(url)

        if scrape_result.status == "ok":
            text = scrape_result.fields.get("visible_text") or ""
            result.scrape_status = "ok"
            result.source = "db+scraper"
            logger.info("medicine_verify._scrape | ok chars=%d", len(text))
            return text or None

        result.scrape_status = scrape_result.status
        logger.info("medicine_verify._scrape | failed status=%s", scrape_result.status)
        result.notes.append(
            f"Manufacturer portal scrape failed ({scrape_result.status}). "
            "Using web search as fallback."
        )
        return None

    except Exception as exc:
        result.scrape_status = "failed"
        logger.warning("medicine_verify._scrape | exception: %s", exc)
        return None


async def _tavily_fallback(
    result: MedicineVerifyResult,
    barcode_data: str | None,
    ocr_text: str | None,
) -> str | None:
    """
    Search Tavily for medicine details when the scraper has nothing.

    Only runs if scraper status is not "ok". Returns snippet text on success
    (fed to the matcher as the "scraped side") or None if Tavily also fails.
    """
    if result.scrape_status == "ok":
        return None   # scraper succeeded, no fallback needed

    # Build a useful query from whatever we know about the product
    product_name = (
        result.brand_name
        or result.generic_name
        or _extract_product_name_from_ocr(ocr_text)
        or barcode_data
        or ""
    )
    if not product_name.strip():
        logger.info("medicine_verify._tavily_fallback | no product name to search")
        return None

    logger.info("medicine_verify._tavily_fallback | searching for %r", product_name[:60])

    try:
        from services.search.tavily import search_medicine_info
        batch_no = (
            (result.batch_info.batch_number if result.batch_info else None)
            or result.extracted_label.get("batch_number")
        )
        tavily_result = await search_medicine_info(
            product_name=product_name,
            batch_no=batch_no,
            manufacturer=result.manufacturer_name,
        )

        if tavily_result.status == "ok" and tavily_result.combined_text:
            result.tavily_used = True
            result.scrape_status = "tavily_fallback"
            result.source = "db+tavily" if result.medicine_id else "tavily_only"
            result.notes.append(
                "Manufacturer portal was unreachable. Used Tavily web search as data source."
            )
            logger.info(
                "medicine_verify._tavily_fallback | ok chars=%d",
                len(tavily_result.combined_text),
            )
            return tavily_result.combined_text

        logger.info(
            "medicine_verify._tavily_fallback | no results status=%s",
            tavily_result.status,
        )

    except Exception as exc:
        logger.warning("medicine_verify._tavily_fallback | failed: %s", exc)

    return None


async def _run_matcher(
    result: MedicineVerifyResult,
    barcode_data: str | None,
    ocr_text: str | None,
    scraped_text: str | None,
) -> None:
    """
    Run the deterministic matcher engine and populate result.verdict.

    Uses services/matcher/engine.py ``match()`` (async). Skipped when we
    already have a definitive verdict (e.g. expired batch).
    """
    try:
        from services.matcher.engine import match

        verdict = await match(
            barcode_payload=barcode_data,
            ocr_text=ocr_text or "",
            scrape_data={"visible_text": scraped_text} if scraped_text else None,
        )

        # Map Verdict dataclass fields to pipeline result
        _LABEL_MAP = {
            "safe":          "VERIFIED",
            "caution":       "SUSPICIOUS",
            "high_risk":     "SUSPICIOUS",
            "unverifiable":  "UNKNOWN",
        }
        result.verdict          = _LABEL_MAP.get(verdict.verdict, "UNKNOWN")
        result.verdict_score    = float(verdict.score) if verdict.score is not None else None
        result.verdict_summary  = verdict.summary or ""
        result.matcher_details  = {
            "label":        verdict.verdict,
            "score":        verdict.score,
            "summary":      verdict.summary,
            "evidence":     verdict.evidence,
            "label_fields": verdict.label_fields,
            "page_fields":  verdict.page_fields,
        }

        if not result.source or result.source == "unknown":
            result.source = "matcher_only"

        logger.info(
            "medicine_verify._run_matcher | label=%s verdict=%s score=%s",
            verdict.verdict, result.verdict, result.verdict_score,
        )

    except Exception as exc:
        logger.warning("medicine_verify._run_matcher | matcher failed: %s", exc)
        result.verdict = "UNKNOWN"
        result.notes.append("Verification engine encountered an error.")


def _extract_product_name_from_ocr(ocr_text: str | None) -> str | None:
    """
    Best-effort extraction of a product name from raw OCR text.

    Looks for the first non-short, non-numeric line as a candidate name.
    Used when we don't have a DB match to pull the brand/generic name from.
    """
    if not ocr_text:
        return None
    for line in ocr_text.splitlines():
        line = line.strip()
        # Skip very short lines, pure numbers, lines that look like addresses
        if len(line) < 4 or line.isdigit():
            continue
        if any(kw in line.lower() for kw in ("mfg", "exp", "batch", "lot", "lic")):
            continue
        return line[:80]
    return None


def _clamp_score(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return round(max(0.0, min(10.0, float(raw))), 2)
    except (TypeError, ValueError):
        return None


def _parse_ym_date(ym_str: str | None) -> date | None:
    """Parse a YYYY-MM string into a date (day=1). Returns None on failure."""
    if not ym_str:
        return None
    try:
        parts = ym_str.replace("/", "-").split("-")
        if len(parts) >= 2:
            return date(int(parts[0]), int(parts[1]), 1)
    except (ValueError, IndexError):
        pass
    return None


_EXTRACT_PROMPT = """\
Extract structured fields from this medicine label OCR text. Return ONLY a valid JSON object — no explanations, no markdown.

OCR text:
{ocr_text}

JSON schema (use null for fields not found):
{{
  "brand_name": "trade/brand name (e.g. Dolo-650)",
  "generic_name": "full generic description (e.g. Paracetamol Tablets IP)",
  "salt": "active ingredient + strength (e.g. Paracetamol IP 650 mg)",
  "batch_number": "B.No. / Batch / Lot value (e.g. DOBSS3975)",
  "mfg_date": "manufacture date as YYYY-MM (e.g. 2025-03)",
  "expiry_date": "expiry date as YYYY-MM (e.g. 2029-02)",
  "manufacturer": "manufacturer company name",
  "license_no": "manufacturing licence number",
  "mrp": "MRP if printed"
}}"""


async def _gemini_extract_label(ocr_text: str) -> dict[str, Any]:
    """
    Call Gemini (text mode) to parse raw OCR text into structured label fields.

    Returns an empty dict on any failure so callers never have to handle exceptions.
    Uses a 15-second timeout to avoid blocking the pipeline.
    """
    if not ocr_text.strip():
        return {}
    try:
        from app.core.config import get_settings
        s = get_settings()
        if not s.google_api_key:
            return {}

        from google import genai
        client = genai.Client(api_key=s.google_api_key)
        prompt = _EXTRACT_PROMPT.format(ocr_text=ocr_text[:3000])

        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=s.google_vision_model,
                contents=[prompt],
            ),
            timeout=15.0,
        )
        raw = (response.text or "").strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        # Extract the JSON object from the response
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return {}
        extracted: dict[str, Any] = json.loads(raw[start:end])
        # Remove null values so callers can use simple `or` checks
        return {k: v for k, v in extracted.items() if v is not None}

    except Exception as exc:
        logger.warning("medicine_verify._gemini_extract_label | failed: %s", exc)
        return {}
