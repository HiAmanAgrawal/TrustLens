"""
Scan endpoints — the primary consumer-facing feature.

Phase 1/2 (unchanged):
  POST /v1/scan/image   — photo → decode → OCR → matcher → verdict
  POST /v1/scan/code    — typed barcode → matcher → verdict
  GET  /v1/scan/history — user scan history

Phase 3 (new):
  POST /v1/scan/prescription — Rx image → extract medicines → pgvector match
  POST /v1/scan/unified      — any image/code → auto-classify → pipeline
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.api.deps import DBSession, OptionalUser
from app.schemas.common import TrustLensResponse
from app.schemas.pipeline import PrescriptionScanResponse, UnifiedScanResponse
from app.schemas.scan_event import ScanEventRead, ScanEventSummary

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Phase 1/2 — unchanged
# ---------------------------------------------------------------------------

@router.post(
    "/image",
    response_model=TrustLensResponse[ScanEventRead],
    status_code=status.HTTP_200_OK,
    summary="Scan a medicine product image",
)
async def scan_image(
    session: DBSession,
    current_user: OptionalUser,
    image: Annotated[UploadFile, File(description="JPEG/PNG of the product or its barcode")],
    lang: Annotated[str, Form()] = "en",
):
    """
    Full medicine image pipeline:
      1. Decode barcode / QR code (WeChat detector → pyzbar fallback).
      2. Extract text from label (Gemini Vision → Tesseract fallback).
      3. Scrape manufacturer portal if a URL is embedded in the QR.
      4. Run matcher to compare label ↔ scraped fields.
      5. Persist scan event and return verdict.

    For auto-classified input (medicine OR grocery), use /v1/scan/unified.
    """
    logger.info(
        "POST /v1/scan/image | user_id=%s content_type=%s lang=%s",
        current_user.id if current_user else "anonymous",
        image.content_type,
        lang,
    )

    image_bytes = await image.read()
    logger.info("scan.image_read | size=%d bytes", len(image_bytes))

    from services.barcode.decoder import decode as barcode_decode
    barcode_data: str | None = None
    decode_result = barcode_decode(image_bytes)
    if decode_result:
        barcode_data = decode_result[0]
        logger.info("scan.barcode_decoded | data=%r", barcode_data)
    else:
        logger.info("scan.barcode_not_found | falling back to OCR-only")

    from services.ocr.extractor import extract_text
    ocr_result = await extract_text(image_bytes)
    ocr_text = ocr_result.text if ocr_result else None
    logger.info(
        "scan.ocr_done | chars=%d confidence=%.2f",
        len(ocr_text or ""), ocr_result.confidence if ocr_result else 0.0,
    )

    scraped_text: str | None = None
    if barcode_data and barcode_data.startswith(("http://", "https://")):
        logger.info("scan.scraping | url=%r", barcode_data)
        from services.scraper.agent import scrape_url
        scrape_result = await scrape_url(barcode_data)
        if scrape_result.status == "ok":
            scraped_text = scrape_result.fields.get("visible_text")
            logger.info("scan.scrape_ok | chars=%d", len(scraped_text or ""))
        else:
            logger.warning("scan.scrape_failed | status=%s", scrape_result.status)

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
    summary="Look up a medicine by typed barcode / QR string",
)
async def scan_code(
    session: DBSession,
    current_user: OptionalUser,
    code: Annotated[str, Form(min_length=1, max_length=500)],
    lang: Annotated[str, Form()] = "en",
):
    """
    Code-only path — skips image decode and OCR.
    For full medicine verification with Tavily fallback, use /v1/scan/unified.
    """
    logger.info(
        "POST /v1/scan/code | user_id=%s code=%r lang=%s",
        current_user.id if current_user else "anonymous",
        code[:40],
        lang,
    )

    scraped_text: str | None = None
    if code.startswith(("http://", "https://")):
        from services.scraper.agent import scrape_url
        scrape_result = await scrape_url(code)
        scraped_text = scrape_result.fields.get("visible_text") if scrape_result.status == "ok" else None
        logger.info(
            "scan.code_scrape | status=%s chars=%d",
            scrape_result.status, len(scraped_text or ""),
        )

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
    summary="User's scan history (all pipeline types)",
)
async def scan_history(
    session: DBSession,
    current_user: OptionalUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Return the current user's scan history (medicine + grocery + prescription), newest first."""
    if not current_user:
        return TrustLensResponse.success([])

    logger.info(
        "GET /v1/scan/history | user_id=%s limit=%d offset=%d",
        current_user.id, limit, offset,
    )
    from app.services.scan_service import list_user_scan_history
    events = await list_user_scan_history(session, current_user.id, limit=limit, offset=offset)
    return TrustLensResponse.success([ScanEventSummary.model_validate(e) for e in events])


# ---------------------------------------------------------------------------
# Phase 3 — new endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/prescription",
    response_model=TrustLensResponse[PrescriptionScanResponse],
    status_code=status.HTTP_200_OK,
    summary="Extract medicine list from a prescription image",
)
async def scan_prescription(
    session: DBSession,
    current_user: OptionalUser,
    image: Annotated[
        UploadFile,
        File(description="JPEG/PNG of the prescription — handwritten or typed"),
    ],
    lang: Annotated[str, Form()] = "en",
):
    """
    Prescription OCR pipeline:
      1. Gemini Vision → structured JSON (doctor, patient, medicines with dosage/frequency).
      2. Tesseract + regex fallback if Gemini is unavailable.
      3. pgvector cosine-similarity search maps each medicine name to the DB.
      4. Returns clean medicine cards; unmatched medicines shown as "not in database".

    SCOPE GUARDRAIL: Displays what the prescription says. Never suggests
      alternatives, diagnoses conditions, or recommends dosage changes.
    """
    logger.info(
        "POST /v1/scan/prescription | user_id=%s",
        current_user.id if current_user else "anonymous",
    )

    image_bytes = await image.read()
    if not image_bytes:
        from app.core.exceptions import InvalidInputError
        raise InvalidInputError("Empty image upload.")

    logger.info("scan.prescription.read | size=%d bytes", len(image_bytes))

    from app.services.pipeline_service import run_prescription_scan
    response = await run_prescription_scan(
        session,
        image_bytes=image_bytes,
        user_id=current_user.id if current_user else None,
    )
    logger.info(
        "scan.prescription.done | medicines=%d method=%s",
        len(response.medicine_cards), response.extraction_method,
    )
    return TrustLensResponse.success(response)


@router.post(
    "/unified",
    response_model=TrustLensResponse[UnifiedScanResponse],
    status_code=status.HTTP_200_OK,
    summary="Auto-classify any product image and run the matching pipeline",
)
async def scan_unified(
    session: DBSession,
    current_user: OptionalUser,
    image: Annotated[
        UploadFile,
        File(description="JPEG/PNG of any product — medicine, grocery, or prescription"),
    ],
    lang: Annotated[str, Form()] = "en",
    scan_type: Annotated[str | None, Form()] = None,
):
    """
    Unified scan pipeline — recommended for new integrations.

    Steps:
      1. Barcode decode (WeChat → pyzbar fallback).
      2. OCR (Gemini Vision → Tesseract fallback).
      3. Classify: prescription | medicine | grocery | unknown.
      4. Run appropriate pipeline (with Tavily fallback on scrape failure).
      5. Persist scan event.
      6. Return verdict, expiry status, FSSAI check, allergen warnings, storage tips.

    Pass ``scan_type`` form field to override auto-classification:
      "prescription" | "medicine" | "grocery"
    """
    logger.info(
        "POST /v1/scan/unified | user_id=%s scan_type=%s lang=%s",
        current_user.id if current_user else "anonymous",
        scan_type,
        lang,
    )

    image_bytes = await image.read()
    if not image_bytes:
        from app.core.exceptions import InvalidInputError
        raise InvalidInputError("Empty image upload.")

    logger.info("scan.unified.read | size=%d bytes", len(image_bytes))

    # Barcode decode up front — symbology is needed for the classifier
    from services.barcode.decoder import decode as barcode_decode
    barcode_data: str | None = None
    barcode_symbology: str | None = None
    decoded = barcode_decode(image_bytes)
    if decoded:
        barcode_data = decoded[0]
        barcode_symbology = decoded[1] if len(decoded) > 1 else None
        logger.info(
            "scan.unified.barcode | data=%r symbology=%s",
            barcode_data, barcode_symbology,
        )
    else:
        logger.info("scan.unified.barcode | not found")

    # User allergens for grocery cross-check
    user_allergens: list[str] = []
    if current_user:
        try:
            from app.services.user_service import list_allergies
            allergies = await list_allergies(session, current_user.id)
            user_allergens = [a.allergen.lower() for a in allergies]
            logger.info(
                "scan.unified.allergens | user_id=%s count=%d",
                current_user.id, len(user_allergens),
            )
        except Exception as exc:
            logger.warning("scan.unified.allergens_fetch_failed | %s", exc)

    from app.services.pipeline_service import run_unified_scan
    response = await run_unified_scan(
        session,
        image_bytes=image_bytes,
        barcode_data=barcode_data,
        barcode_symbology=barcode_symbology,
        scan_type_hint=scan_type,
        user_id=current_user.id if current_user else None,
        user_allergens=user_allergens,
        lang=lang,
    )

    logger.info(
        "scan.unified.done | scan_type=%s verdict=%s expiry=%s",
        response.scan_type, response.verdict, response.expiry_status,
    )
    return TrustLensResponse.success(response)
