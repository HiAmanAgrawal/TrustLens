"""Grocery item CRUD and analysis endpoints."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.api.deps import CurrentUser, DBSession, OptionalUser
from app.schemas.common import TrustLensResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/scan",
    status_code=status.HTTP_200_OK,
    summary="Scan a grocery product image and return safety analysis",
)
async def scan_grocery(
    session: DBSession,
    current_user: OptionalUser,
    image: Annotated[UploadFile, File()],
    lang: str = "en",
):
    """
    Grocery scan pipeline:
      1. Decode barcode.
      2. OCR the label.
      3. Run grocery analyzer (claims, nutrition, expiry, FSSAI, ingredients).
      4. Return structured analysis + allergen flags for the user's profile.

    WHY a separate endpoint from /scan/image:
      Medicine and grocery have completely different analysis pipelines.
      The classifier determines which pipeline runs, but we expose separate
      endpoints so clients can choose explicitly (e.g., grocery-only app).
    """
    logger.info(
        "POST /v1/grocery/scan | user_id=%s",
        current_user.id if current_user else "anonymous",
    )
    image_bytes = await image.read()

    # Barcode decode
    from services.barcode.decoder import decode as barcode_decode
    decoded = barcode_decode(image_bytes)
    barcode_data = decoded[0] if decoded else None
    logger.info("grocery.scan.barcode | data=%r", barcode_data)

    # OCR
    from services.ocr.extractor import extract_text
    ocr_result = await extract_text(image_bytes)
    label_text = ocr_result.text if ocr_result else ""
    logger.info("grocery.scan.ocr | chars=%d", len(label_text))

    # Grocery analyzer
    from services.grocery.analyzer import analyze
    analysis = await analyze(label_text=label_text, barcode=barcode_data)
    logger.info(
        "grocery.scan.analysis_done | fssai_valid=%s expiry_safe=%s",
        analysis.get("fssai", {}).get("is_valid"),
        analysis.get("dates", {}).get("is_safe"),
    )

    # Allergen cross-check against user profile
    allergen_warnings: list[str] = []
    if current_user and analysis.get("ingredients"):
        from app.services.user_service import list_allergies
        user_allergies = await list_allergies(session, current_user.id)
        user_allergen_names = {a.allergen.lower() for a in user_allergies}
        for ingredient_entry in analysis["ingredients"].get("flagged", []):
            if ingredient_entry.get("name", "").lower() in user_allergen_names:
                allergen_warnings.append(ingredient_entry["name"])
        if allergen_warnings:
            logger.warning(
                "grocery.scan.allergen_warning | user_id=%s allergens=%s",
                current_user.id, allergen_warnings,
            )

    return TrustLensResponse.success({
        "barcode": barcode_data,
        "analysis": analysis,
        "allergen_warnings": allergen_warnings,
        "lang": lang,
    })
