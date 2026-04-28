"""
Grocery scan endpoint — Phase 3.

POST /v1/grocery/scan

Phase 3 upgrade: replaces the raw dict response with typed GroceryScanResponse
and routes through the new pipeline_service which adds:
  - Tavily FSSAI verification fallback
  - Structured ExpiryStatus (SAFE | NEAR_EXPIRY | EXPIRED | UNKNOWN)
  - Storage condition extraction
  - Allergen cross-check against user profile
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.api.deps import DBSession, OptionalUser
from app.schemas.common import TrustLensResponse
from app.schemas.pipeline import GroceryScanResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/scan",
    response_model=TrustLensResponse[GroceryScanResponse],
    status_code=status.HTTP_200_OK,
    summary="Scan a grocery product label",
)
async def scan_grocery(
    session: DBSession,
    current_user: OptionalUser,
    image: Annotated[UploadFile, File()],
    lang: str = "en",
):
    """
    Grocery scan pipeline (Phase 3):
      1. Barcode decode.
      2. OCR (Gemini Vision → Tesseract fallback).
      3. Static analysis: dates, nutrition, ingredients, claims.
      4. FSSAI verification: Playwright FoSCoS → Tavily web search fallback.
      5. Allergen cross-check against the logged-in user's profile.
      6. Storage condition extraction.
      7. Structured risk band: low | medium | high | unknown.

    Expiry status:
      SAFE        — expiry > 30 days away.
      NEAR_EXPIRY — expires within 30 days.
      EXPIRED     — expiry date has passed.
      UNKNOWN     — no date found on label.
    """
    logger.info(
        "POST /v1/grocery/scan | user_id=%s lang=%s",
        current_user.id if current_user else "anonymous",
        lang,
    )

    image_bytes = await image.read()
    if not image_bytes:
        from app.core.exceptions import InvalidInputError
        raise InvalidInputError("Empty image upload.")

    logger.info("grocery.scan.read | size=%d bytes", len(image_bytes))

    # Barcode decode (symbology not needed for the grocery pipeline)
    from services.barcode.decoder import decode as barcode_decode
    decoded = barcode_decode(image_bytes)
    barcode_data = decoded[0] if decoded else None
    logger.info("grocery.scan.barcode | data=%r", barcode_data)

    # Load user allergen list for cross-check
    user_allergens: list[str] = []
    if current_user:
        try:
            from app.services.user_service import list_allergies
            allergies = await list_allergies(session, current_user.id)
            user_allergens = [a.allergen.lower() for a in allergies]
            logger.info(
                "grocery.scan.allergens | user_id=%s count=%d",
                current_user.id, len(user_allergens),
            )
        except Exception as exc:
            logger.warning("grocery.scan.allergens_fetch_failed | %s", exc)

    from app.services.pipeline_service import run_grocery_scan
    _, response = await run_grocery_scan(
        session,
        image_bytes=image_bytes,
        barcode_data=barcode_data,
        user_id=current_user.id if current_user else None,
        user_allergens=user_allergens,
    )

    logger.info(
        "grocery.scan.done | risk=%s expiry=%s fssai=%s allergens=%d",
        response.risk_band,
        response.expiry_status,
        response.fssai.online_status if response.fssai else "none",
        len(response.allergen_warnings),
    )
    return TrustLensResponse.success(response)
