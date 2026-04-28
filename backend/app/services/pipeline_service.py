"""
PipelineService — DB-aware orchestration layer for Phase 3 scan pipelines.

This service bridges the framework-agnostic ``services/pipeline/`` package
(no DB writes) with the SQLAlchemy session so results are persisted as
``MedicineScanEvent`` rows for audit, history, and analytics.

Responsibilities:
  1. Call ``services/pipeline/router.route_and_run()`` to get the raw result.
  2. Map the result back to a ``MedicineScanEvent`` (or skip for prescriptions,
     which don't have a binary verdict).
  3. Return both the persisted event (for history) and the typed pipeline result
     (for the API response).

WHY a separate service instead of doing this in the route:
  - Routes stay thin (no business logic, no ORM imports).
  - This service can be called from the WhatsApp webhook handler without
    duplicating the persisting logic.
  - Makes the pipeline testable with a mock session.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuthenticityVerdictEnum
from app.models.scan_event import MedicineScanEvent
from app.schemas.pipeline import (
    GroceryScanResponse,
    MedicineScanResponse,
    PrescriptionScanResponse,
    StorageWarningSchema,
    UnifiedScanResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prescription pipeline
# ---------------------------------------------------------------------------

async def run_prescription_scan(
    session: AsyncSession,
    *,
    image_bytes: bytes,
    user_id: uuid.UUID | None = None,
) -> PrescriptionScanResponse:
    """
    Run prescription OCR + vector search. No scan event persisted — prescription
    scans are read-only (we extract and display, never flag as authentic/counterfeit).
    """
    logger.info("pipeline_service.prescription | user_id=%s bytes=%d", user_id, len(image_bytes))

    from services.pipeline.prescription import extract_prescription
    result = await extract_prescription(image_bytes, session=session)

    return PrescriptionScanResponse(
        doctor_name=result.doctor_name,
        patient_name=result.patient_name,
        prescription_date=result.prescription_date,
        hospital_clinic=result.hospital_clinic,
        medicine_cards=[_card_to_schema(c) for c in result.medicine_cards],
        extraction_method=result.extraction_method,
        confidence=result.confidence,
        notes=result.notes,
    )


# ---------------------------------------------------------------------------
# Medicine verification pipeline
# ---------------------------------------------------------------------------

async def run_medicine_scan(
    session: AsyncSession,
    *,
    barcode_data: str | None,
    ocr_text: str | None,
    user_id: uuid.UUID | None = None,
    country_code: str | None = None,
    lang: str = "en",
) -> tuple[MedicineScanEvent, MedicineScanResponse]:
    """
    Run medicine verification and persist a MedicineScanEvent.

    Returns (event, response) — the route layer serialises the response and
    can use the event ID for the scan_event_id field.
    """
    logger.info(
        "pipeline_service.medicine | user_id=%s barcode=%r",
        user_id, (barcode_data or "")[:40],
    )

    from services.pipeline.medicine_verify import verify_medicine
    med_result = await verify_medicine(
        barcode_data=barcode_data,
        ocr_text=ocr_text,
        session=session,
        lang=lang,
    )

    verdict_enum = _str_to_verdict(med_result.verdict)
    event = MedicineScanEvent(
        user_id=user_id,
        medicine_id=uuid.UUID(med_result.medicine_id) if med_result.medicine_id else None,
        batch_id=uuid.UUID(med_result.batch_id) if med_result.batch_id else None,
        barcode_data=barcode_data,
        ocr_text=(ocr_text or "")[:5000],
        authenticity_verdict=verdict_enum,
        verdict_score=med_result.verdict_score,
        verdict_details={
            **med_result.matcher_details,
            "source": med_result.source,
            "tavily_used": med_result.tavily_used,
            "scrape_status": med_result.scrape_status,
            "storage_warnings": [
                {"condition": w.condition, "message": w.message}
                for w in med_result.storage_warnings
            ],
        },
        country_code=country_code,
        scan_type="medicine",
    )
    session.add(event)
    await session.flush()

    logger.info(
        "pipeline_service.medicine.persisted | event_id=%s verdict=%s",
        event.id, verdict_enum,
    )

    response = MedicineScanResponse(
        scan_event_id=str(event.id),
        verdict=med_result.verdict,
        verdict_score=med_result.verdict_score,
        verdict_summary=med_result.verdict_summary,
        medicine_id=med_result.medicine_id,
        brand_name=med_result.brand_name,
        generic_name=med_result.generic_name,
        manufacturer_name=med_result.manufacturer_name,
        batch_info=_batch_info_schema(med_result.batch_info),
        expiry_status=_derive_medicine_expiry(med_result),
        source=med_result.source,
        tavily_used=med_result.tavily_used,
        storage_warnings=[_storage_schema(w) for w in med_result.storage_warnings],
        notes=med_result.notes,
        extracted_label=med_result.extracted_label or None,
        ocr_text=(ocr_text or "")[:2000] if ocr_text else None,
    )
    return event, response


# ---------------------------------------------------------------------------
# Grocery verification pipeline
# ---------------------------------------------------------------------------

async def run_grocery_scan(
    session: AsyncSession,
    *,
    image_bytes: bytes | None = None,
    ocr_text: str | None = None,
    barcode_data: str | None = None,
    user_id: uuid.UUID | None = None,
    user_allergens: list[str] | None = None,
    country_code: str | None = None,
) -> tuple[MedicineScanEvent, GroceryScanResponse]:
    """
    Run grocery verification and persist a scan event.

    We reuse MedicineScanEvent for grocery scans with scan_type="grocery"
    to keep a single audit table and history endpoint.
    """
    logger.info(
        "pipeline_service.grocery | user_id=%s barcode=%r",
        user_id, (barcode_data or "")[:40],
    )

    from services.pipeline.grocery_verify import verify_grocery
    groc_result = await verify_grocery(
        image_bytes=image_bytes,
        ocr_text=ocr_text,
        barcode_data=barcode_data,
        user_allergens=user_allergens or [],
    )

    # Map grocery risk_band → authenticity verdict for the unified events table
    verdict_enum = _risk_to_verdict(groc_result.risk_band)

    event = MedicineScanEvent(
        user_id=user_id,
        barcode_data=barcode_data,
        ocr_text=(ocr_text or "")[:5000],
        authenticity_verdict=verdict_enum,
        verdict_score=None,
        verdict_details={
            "risk_band": groc_result.risk_band,
            "expiry_status": groc_result.expiry_status,
            "fssai": {
                "license_number": groc_result.fssai.license_number,
                "online_status": groc_result.fssai.online_status,
            } if groc_result.fssai else None,
            "allergen_warnings": groc_result.allergen_warnings,
            "storage_warnings": [
                {"condition": w.condition, "message": w.message}
                for w in groc_result.storage_warnings
            ],
        },
        country_code=country_code,
        scan_type="grocery",
    )
    session.add(event)
    await session.flush()

    logger.info(
        "pipeline_service.grocery.persisted | event_id=%s verdict=%s risk=%s",
        event.id, verdict_enum, groc_result.risk_band,
    )

    fssai_schema = None
    if groc_result.fssai:
        from app.schemas.pipeline import FssaiVerifySchema
        f = groc_result.fssai
        fssai_schema = FssaiVerifySchema(
            license_number=f.license_number,
            format_valid=f.format_valid,
            online_status=f.online_status,
            business_name=f.business_name,
            expiry=f.expiry,
            verify_url=f.verify_url,
            tavily_used=f.tavily_used,
        )

    from app.schemas.pipeline import FindingSchema
    # Phase 4: compute trust score from the product context
    from app.services.product_context import build_context_from_grocery_response
    from app.services.trust_score_service import compute_trust_score

    _tmp_response = GroceryScanResponse(
        risk_band=groc_result.risk_band,
        expiry_status=groc_result.expiry_status,
        dates=groc_result.dates,
        findings=[
            FindingSchema(
                code=f.get("code", ""),
                severity=f.get("severity", "info"),
                message=f.get("message", ""),
                evidence=f.get("evidence"),
            )
            for f in groc_result.findings
        ],
        fssai=fssai_schema,
        ingredients_count=groc_result.ingredients_count,
        ingredients=groc_result.ingredients,
        allergen_warnings=groc_result.allergen_warnings,
        storage_warnings=[_storage_schema(w) for w in groc_result.storage_warnings],
        product_extraction=_extraction_schema(groc_result.product_extraction),
        barcode_data=barcode_data,
        notes=groc_result.notes,
    )
    product_ctx = build_context_from_grocery_response(_tmp_response, session_id="pipeline")
    ts = compute_trust_score(product_ctx)

    response = _tmp_response.model_copy(update={
        "trust_score": ts.score,
        "trust_label": ts.label,
        "trust_reasons": ts.reasons,
    })
    return event, response


# ---------------------------------------------------------------------------
# Unified scan pipeline
# ---------------------------------------------------------------------------

async def run_unified_scan(
    session: AsyncSession,
    *,
    image_bytes: bytes | None = None,
    ocr_text: str | None = None,
    barcode_data: str | None = None,
    barcode_symbology: str | None = None,
    scan_type_hint: str | None = None,
    user_id: uuid.UUID | None = None,
    user_allergens: list[str] | None = None,
    country_code: str | None = None,
    lang: str = "en",
) -> UnifiedScanResponse:
    """
    Auto-classify the input and run the right pipeline.

    This is the backend of POST /v1/scan/unified — it hides the routing
    logic from the route handler and returns a fully typed UnifiedScanResponse.
    """
    logger.info(
        "pipeline_service.unified | user_id=%s hint=%s barcode=%r",
        user_id, scan_type_hint, (barcode_data or "")[:40],
    )

    from services.pipeline.router import route_and_run
    unified = await route_and_run(
        image_bytes=image_bytes,
        ocr_text=ocr_text,
        barcode_data=barcode_data,
        barcode_symbology=barcode_symbology,
        scan_type_hint=scan_type_hint,
        user_allergens=user_allergens,
        session=session,
        lang=lang,
    )

    # Persist a scan event for non-prescription types
    scan_event_id: str | None = None
    if unified.scan_type == "medicine" and unified.medicine_result:
        m = unified.medicine_result
        verdict_enum = _str_to_verdict(m.verdict)
        event = MedicineScanEvent(
            user_id=user_id,
            medicine_id=uuid.UUID(m.medicine_id) if m.medicine_id else None,
            batch_id=uuid.UUID(m.batch_id) if m.batch_id else None,
            barcode_data=barcode_data,
            ocr_text=(ocr_text or "")[:5000],
            authenticity_verdict=verdict_enum,
            verdict_score=m.verdict_score,
            verdict_details=m.matcher_details,
            country_code=country_code,
            scan_type="medicine",
        )
        session.add(event)
        await session.flush()
        scan_event_id = str(event.id)
        logger.info("pipeline_service.unified.persisted | event_id=%s", scan_event_id)

    elif unified.scan_type == "grocery" and unified.grocery_result:
        g = unified.grocery_result
        event = MedicineScanEvent(
            user_id=user_id,
            barcode_data=barcode_data,
            ocr_text=(ocr_text or "")[:5000],
            authenticity_verdict=_risk_to_verdict(g.risk_band),
            verdict_details={"risk_band": g.risk_band, "expiry_status": g.expiry_status},
            country_code=country_code,
            scan_type="grocery",
        )
        session.add(event)
        await session.flush()
        scan_event_id = str(event.id)

    # Build unified response
    resp = UnifiedScanResponse(
        scan_type=unified.scan_type,
        category=unified.category,
        scan_event_id=scan_event_id,
        verdict=unified.verdict,
        verdict_score=unified.verdict_score,
        expiry_status=unified.expiry_status,
        storage_warnings=[_storage_schema(w) for w in unified.storage_warnings],
        notes=unified.notes,
    )

    # Populate typed sub-response
    if unified.prescription_result:
        prx = unified.prescription_result
        from app.schemas.pipeline import PrescriptionScanResponse
        resp.prescription = PrescriptionScanResponse(
            doctor_name=prx.doctor_name,
            patient_name=prx.patient_name,
            prescription_date=prx.prescription_date,
            hospital_clinic=prx.hospital_clinic,
            medicine_cards=[_card_to_schema(c) for c in prx.medicine_cards],
            extraction_method=prx.extraction_method,
            confidence=prx.confidence,
            notes=prx.notes,
        )

    elif unified.medicine_result:
        m = unified.medicine_result
        resp.medicine = MedicineScanResponse(
            scan_event_id=scan_event_id,
            verdict=m.verdict,
            verdict_score=m.verdict_score,
            verdict_summary=m.verdict_summary,
            medicine_id=m.medicine_id,
            brand_name=m.brand_name,
            generic_name=m.generic_name,
            manufacturer_name=m.manufacturer_name,
            batch_info=_batch_info_schema(m.batch_info),
            expiry_status=unified.expiry_status or "UNKNOWN",
            source=m.source,
            tavily_used=m.tavily_used,
            storage_warnings=[_storage_schema(w) for w in m.storage_warnings],
            notes=m.notes,
            extracted_label=m.extracted_label or None,
            ocr_text=(ocr_text or "")[:2000] if ocr_text else None,
        )

    elif unified.grocery_result:
        g = unified.grocery_result
        from app.schemas.pipeline import FssaiVerifySchema, FindingSchema
        fssai_s = None
        if g.fssai:
            fssai_s = FssaiVerifySchema(
                license_number=g.fssai.license_number,
                format_valid=g.fssai.format_valid,
                online_status=g.fssai.online_status,
                business_name=g.fssai.business_name,
                expiry=g.fssai.expiry,
                verify_url=g.fssai.verify_url,
                tavily_used=g.fssai.tavily_used,
            )
        resp.grocery = GroceryScanResponse(
            risk_band=g.risk_band,
            expiry_status=g.expiry_status,
            dates=g.dates,
            findings=[
                FindingSchema(
                    code=f.get("code", ""),
                    severity=f.get("severity", "info"),
                    message=f.get("message", ""),
                    evidence=f.get("evidence"),
                )
                for f in g.findings
            ],
            fssai=fssai_s,
            ingredients_count=g.ingredients_count,
            ingredients=g.ingredients,
            allergen_warnings=g.allergen_warnings,
            storage_warnings=[_storage_schema(w) for w in g.storage_warnings],
            product_extraction=_extraction_schema(g.product_extraction),
            barcode_data=barcode_data,
            notes=g.notes,
        )

    return resp


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _str_to_verdict(value: str) -> AuthenticityVerdictEnum:
    try:
        return AuthenticityVerdictEnum(value)
    except ValueError:
        return AuthenticityVerdictEnum.UNKNOWN


def _risk_to_verdict(risk_band: str) -> AuthenticityVerdictEnum:
    return {
        "low": AuthenticityVerdictEnum.VERIFIED,
        "medium": AuthenticityVerdictEnum.SUSPICIOUS,
        "high": AuthenticityVerdictEnum.SUSPICIOUS,
    }.get(risk_band, AuthenticityVerdictEnum.UNKNOWN)


def _derive_medicine_expiry(med_result: Any) -> str:
    if med_result.verdict == "EXPIRED":
        return "EXPIRED"
    if med_result.batch_info and med_result.batch_info.expiry_date:
        from datetime import date as date_cls
        today = date_cls.today()
        exp = med_result.batch_info.expiry_date
        if isinstance(exp, str):
            from datetime import datetime
            try:
                exp = datetime.strptime(exp, "%Y-%m-%d").date()
            except ValueError:
                return "UNKNOWN"
        if exp < today:
            return "EXPIRED"
        if (exp - today).days <= 30:
            return "NEAR_EXPIRY"
        return "SAFE"
    return "UNKNOWN"


def _storage_schema(w: Any) -> StorageWarningSchema:
    return StorageWarningSchema(
        condition=w.condition,
        message=w.message,
        severity=w.severity,
        raw_text=w.raw_text or "",
    )


def _batch_info_schema(b: Any | None) -> Any | None:
    if b is None:
        return None
    from app.schemas.pipeline import BatchInfoSchema
    return BatchInfoSchema(
        batch_id=b.batch_id,
        batch_number=b.batch_number,
        expiry_date=b.expiry_date,
        manufacture_date=b.manufacture_date,
        is_expired=b.is_expired,
    )


def _extraction_schema(ext: Any | None) -> Any | None:
    """Convert a ProductExtraction dataclass to a ProductExtractionSchema Pydantic model."""
    if ext is None or (hasattr(ext, "extraction_method") and ext.extraction_method == "failed"):
        return None
    from app.schemas.pipeline import NutritionSchema, ProductExtractionSchema
    n = ext.nutrition
    return ProductExtractionSchema(
        brand_name=ext.brand_name,
        product_name=ext.product_name,
        product_type=ext.product_type,
        ingredients=ext.ingredients or [],
        ingredients_count=ext.ingredients_count,
        nutrition=NutritionSchema(
            calories_kcal=n.calories_kcal if n else None,
            protein_g=n.protein_g if n else None,
            total_fat_g=n.total_fat_g if n else None,
            saturated_fat_g=n.saturated_fat_g if n else None,
            carbohydrates_g=n.carbohydrates_g if n else None,
            sugar_g=n.sugar_g if n else None,
            dietary_fiber_g=n.dietary_fiber_g if n else None,
            sodium_mg=n.sodium_mg if n else None,
        ) if n else NutritionSchema(),
        serving_size=ext.serving_size,
        servings_per_pack=ext.servings_per_pack,
        positives=ext.positives or [],
        negatives=ext.negatives or [],
        allergens_declared=ext.allergens_declared or [],
        certifications=ext.certifications or [],
        manufacturer=ext.manufacturer,
        net_weight=ext.net_weight,
        is_vegetarian=ext.is_vegetarian,
        is_vegan=ext.is_vegan,
        is_gluten_free=ext.is_gluten_free,
        contains_added_sugar=ext.contains_added_sugar,
        contains_preservatives=ext.contains_preservatives,
        contains_artificial_colours=ext.contains_artificial_colours,
        e_codes_found=ext.e_codes_found or [],
        extraction_method=ext.extraction_method,
    )


def _card_to_schema(c: Any) -> Any:
    from app.schemas.pipeline import MedicineCardSchema, PrescribedMedicineSchema
    return MedicineCardSchema(
        prescribed=PrescribedMedicineSchema(
            raw_name=c.prescribed.raw_name,
            dosage=c.prescribed.dosage,
            frequency=c.prescribed.frequency,
            duration=c.prescribed.duration,
            instructions=c.prescribed.instructions,
        ),
        db_medicine_id=c.db_medicine_id,
        db_brand_name=c.db_brand_name,
        db_generic_name=c.db_generic_name,
        db_dosage_form=c.db_dosage_form,
        db_manufacturer=c.db_manufacturer,
        db_salts=c.db_salts or [],
        match_score=c.match_score,
        found_in_db=c.found_in_db,
    )
