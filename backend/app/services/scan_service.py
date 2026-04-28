"""
ScanService — orchestrates the end-to-end product scan pipeline and persists the result.

This is the highest-level service. It calls barcode, OCR, matcher, and scraper
from the services/ packages, then determines the AuthenticityVerdictEnum and
writes a MedicineScanEvent row. The agent (LangGraph) will eventually replace
some of this logic with tool-calling steps, but the service layer remains the
single place that writes to the DB.

SCOPE GUARDRAIL: We never return a diagnosis or treatment recommendation.
  The verdicts are:
    VERIFIED   — data sources agree, batch is in date.
    SUSPICIOUS — mismatch detected; advise pharmacist check, not medical action.
    EXPIRED    — batch date has passed.
    UNKNOWN    — insufficient data.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import TrustLensError
from app.models.enums import AuthenticityVerdictEnum
from app.models.scan_event import MedicineScanEvent
from app.services.medicine_service import find_by_barcode, is_batch_expired

logger = logging.getLogger(__name__)


async def scan_and_persist(
    session: AsyncSession,
    *,
    barcode_data: str | None,
    ocr_text: str | None,
    matcher_result: dict[str, Any],
    user_id: uuid.UUID | None = None,
    country_code: str | None = None,
) -> MedicineScanEvent:
    """
    Core scan pipeline step: resolve identities, determine verdict, persist event.

    ``matcher_result`` is the dict returned by ``services/matcher/engine.py``
    (keys: score, label, summary, evidence). This service translates the matcher's
    label into our ``AuthenticityVerdictEnum`` and stores the raw result in
    verdict_details for auditability.

    Steps:
      1. Decode barcode → look up Medicine + MedicineBatch.
      2. Check batch expiry (overrides matcher verdict if expired).
      3. Map matcher label → AuthenticityVerdictEnum.
      4. Write MedicineScanEvent row.
      5. Return the event (route will build the API response).
    """
    logger.info(
        "scan_service.scan_and_persist | user_id=%s barcode=%r",
        user_id, barcode_data,
    )

    medicine_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    verdict = AuthenticityVerdictEnum.UNKNOWN
    verdict_score: float | None = None

    # --- Step 1: Resolve product identity from barcode ---
    if barcode_data:
        try:
            match = await find_by_barcode(session, barcode_data)
            if match:
                medicine, batch = match
                medicine_id = medicine.id
                batch_id = batch.id if batch else None
                logger.info(
                    "scan_service.identity_resolved | medicine_id=%s batch_id=%s",
                    medicine_id, batch_id,
                )
        except TrustLensError as exc:
            logger.warning("scan_service.identity_resolution_failed | error=%s", exc)

    # --- Step 2: Check expiry (takes precedence over matcher verdict) ---
    if batch_id is not None:
        from app.services.medicine_service import get_batch_by_id
        batch_obj = await get_batch_by_id(session, batch_id)
        if await is_batch_expired(batch_obj):
            verdict = AuthenticityVerdictEnum.EXPIRED
            logger.info(
                "scan_service.batch_expired | batch_id=%s expiry=%s",
                batch_id, batch_obj.expiry_date,
            )

    # --- Step 3: Map matcher label → verdict (only if not already EXPIRED) ---
    if verdict == AuthenticityVerdictEnum.UNKNOWN:
        verdict = _map_matcher_label(matcher_result.get("label", "unverifiable"))
        verdict_score = _normalize_score(matcher_result.get("score"))
        logger.info(
            "scan_service.verdict_from_matcher | verdict=%s score=%s",
            verdict, verdict_score,
        )

    # --- Step 4: Persist event ---
    event = MedicineScanEvent(
        user_id=user_id,
        medicine_id=medicine_id,
        batch_id=batch_id,
        barcode_data=barcode_data,
        ocr_text=(ocr_text or "")[:5000],   # cap storage; full text in matcher_result
        authenticity_verdict=verdict,
        verdict_score=verdict_score,
        verdict_details=matcher_result,
        country_code=country_code,
    )
    session.add(event)
    await session.flush()
    logger.info(
        "scan_service.event_persisted | event_id=%s verdict=%s", event.id, verdict
    )
    return event


async def list_user_scan_history(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int = 20,
    offset: int = 0,
) -> list[MedicineScanEvent]:
    """Return a user's scan history, newest first."""
    import sqlalchemy as sa
    result = await session.execute(
        sa.select(MedicineScanEvent)
        .where(MedicineScanEvent.user_id == user_id)
        .order_by(MedicineScanEvent.scanned_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MATCHER_LABEL_MAP: dict[str, AuthenticityVerdictEnum] = {
    "safe": AuthenticityVerdictEnum.VERIFIED,
    "caution": AuthenticityVerdictEnum.SUSPICIOUS,
    "high_risk": AuthenticityVerdictEnum.SUSPICIOUS,
    "unverifiable": AuthenticityVerdictEnum.UNKNOWN,
}


def _map_matcher_label(label: str) -> AuthenticityVerdictEnum:
    """
    Translate the matcher engine's text label into our authenticity verdict enum.

    The matcher uses qualitative labels ("safe", "caution", "high_risk",
    "unverifiable") while our API and DB use a cleaner four-value enum.
    Both "caution" and "high_risk" map to SUSPICIOUS — we surface the score
    separately for clients that want more granularity.
    """
    return _MATCHER_LABEL_MAP.get(label, AuthenticityVerdictEnum.UNKNOWN)


def _normalize_score(raw: Any) -> float | None:
    """Clamp the matcher score to [0, 10]; return None if absent/invalid."""
    if raw is None:
        return None
    try:
        return round(max(0.0, min(10.0, float(raw))), 2)
    except (TypeError, ValueError):
        return None
