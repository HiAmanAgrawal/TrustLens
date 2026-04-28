"""
Scan endpoints — the primary consumer-facing feature.

POST /v1/scan/image  — photo upload → decode → OCR → matcher → verdict
POST /v1/scan/code   — typed barcode → matcher → verdict
GET  /v1/scan/history — user's scan history

These endpoints integrate the existing services/barcode, services/ocr, and
services/matcher packages (from the pre-Phase-1 codebase) with the new
database persistence layer added in Phase 1.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.api.deps import DBSession, OptionalUser
from app.schemas.common import TrustLensResponse
from app.schemas.scan_event import ScanEventRead, ScanEventSummary

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/image",
    response_model=TrustLensResponse[ScanEventRead],
    status_code=status.HTTP_200_OK,
    summary="Scan a product image",
)
async def scan_image(
    session: DBSession,
    current_user: OptionalUser,
    image: Annotated[UploadFile, File(description="JPEG/PNG of the product or its barcode")],
    lang: Annotated[str, Form()] = "en",
):
    """
    Full image pipeline:
      1. Decode barcode / QR code (WeChat detector → pyzbar fallback).
      2. Extract text from label (Gemini Vision → Tesseract fallback).
      3. Scrape manufacturer portal if a URL is embedded in the QR.
      4. Run matcher to compare label ↔ scraped fields.
      5. Persist scan event and return verdict.

    Logs every step so failed scans are diagnosable in Logflare/Supabase.
    """
    logger.info(
        "POST /v1/scan/image | user_id=%s content_type=%s lang=%s",
        current_user.id if current_user else "anonymous",
        image.content_type,
        lang,
    )

    image_bytes = await image.read()
    logger.info("scan.image_read | size=%d bytes", len(image_bytes))

    # --- Step 1: Barcode decode ---
    from services.barcode.decoder import decode as barcode_decode
    barcode_data: str | None = None
    decode_result = barcode_decode(image_bytes)
    if decode_result:
        barcode_data = decode_result[0]
        logger.info("scan.barcode_decoded | data=%r", barcode_data)
    else:
        logger.info("scan.barcode_not_found | falling back to OCR-only")

    # --- Step 2: OCR ---
    from services.ocr.extractor import extract_text
    ocr_result = await extract_text(image_bytes)
    ocr_text = ocr_result.text if ocr_result else None
    logger.info("scan.ocr_done | chars=%d confidence=%.2f",
                len(ocr_text or ""), ocr_result.confidence if ocr_result else 0.0)

    # --- Step 3: Scrape (if barcode contains a URL) ---
    scraped_text: str | None = None
    if barcode_data and barcode_data.startswith("http"):
        logger.info("scan.scraping | url=%r", barcode_data)
        from services.scraper.agent import scrape_url
        scrape_result = await scrape_url(barcode_data)
        if scrape_result.status == "ok":
            scraped_text = scrape_result.fields.get("visible_text")
            logger.info("scan.scrape_ok | chars=%d", len(scraped_text or ""))
        else:
            logger.warning("scan.scrape_failed | status=%s", scrape_result.status)

    # --- Step 4: Matcher ---
    from services.matcher.engine import compare
    matcher_result = compare(
        barcode_payload={"data": barcode_data} if barcode_data else {},
        label_text=ocr_text or "",
        scraped_text=scraped_text or "",
    )
    logger.info(
        "scan.matcher_done | label=%s score=%s",
        matcher_result.get("label"), matcher_result.get("score"),
    )

    # --- Step 5: Persist & return ---
    from app.services.scan_service import scan_and_persist
    event = await scan_and_persist(
        session,
        barcode_data=barcode_data,
        ocr_text=ocr_text,
        matcher_result=matcher_result,
        user_id=current_user.id if current_user else None,
    )
    return TrustLensResponse.success(ScanEventRead.model_validate(event))


@router.post(
    "/code",
    response_model=TrustLensResponse[ScanEventRead],
    summary="Look up a product by typed barcode code",
)
async def scan_code(
    session: DBSession,
    current_user: OptionalUser,
    code: Annotated[str, Form(min_length=1, max_length=500)],
    lang: Annotated[str, Form()] = "en",
):
    """
    Code-only path — skips image decode and OCR.
    The matcher runs against scraped data only (label text is empty string).
    """
    logger.info(
        "POST /v1/scan/code | user_id=%s code=%r lang=%s",
        current_user.id if current_user else "anonymous",
        code[:40],
        lang,
    )

    scraped_text: str | None = None
    if code.startswith("http"):
        from services.scraper.agent import scrape_url
        scrape_result = await scrape_url(code)
        scraped_text = scrape_result.fields.get("visible_text") if scrape_result.status == "ok" else None

    from services.matcher.engine import compare
    matcher_result = compare(
        barcode_payload={"data": code},
        label_text="",
        scraped_text=scraped_text or "",
    )
    logger.info("scan.code_matcher_done | label=%s", matcher_result.get("label"))

    from app.services.scan_service import scan_and_persist
    event = await scan_and_persist(
        session,
        barcode_data=code,
        ocr_text=None,
        matcher_result=matcher_result,
        user_id=current_user.id if current_user else None,
    )
    return TrustLensResponse.success(ScanEventRead.model_validate(event))


@router.get(
    "/history",
    response_model=TrustLensResponse[list[ScanEventSummary]],
    summary="User's scan history",
)
async def scan_history(
    session: DBSession,
    current_user: OptionalUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if not current_user:
        return TrustLensResponse.success([])

    logger.info("GET /v1/scan/history | user_id=%s limit=%d offset=%d", current_user.id, limit, offset)
    from app.services.scan_service import list_user_scan_history
    events = await list_user_scan_history(session, current_user.id, limit=limit, offset=offset)
    return TrustLensResponse.success([ScanEventSummary.model_validate(e) for e in events])
