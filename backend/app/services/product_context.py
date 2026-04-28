"""
Product context store — persists the last scanned product's structured data
so the LangGraph product advisor can reference it across follow-up questions.

WHY Redis (not request-scoped):
  The scan and the follow-up questions are separate HTTP requests. Redis gives
  per-session state with automatic expiry so we never accumulate stale data.
  Falls back to an in-process LRU dict when Redis is unavailable (e.g. local
  dev without Redis running).

KEY SCHEMA:
  "trustlens:product_ctx:{session_id}"  →  JSON blob
  TTL: 2 hours (enough for a shopping trip conversation)

CONTEXT SHAPE:
  The stored context is a dict with all the information the advisor agent
  needs to answer follow-up questions without another DB / network call.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_CTX_PREFIX = "trustlens:product_ctx"
_CTX_TTL_S = 7_200     # 2 hours
_MAX_MEMORY = 256       # in-process fallback LRU size

# In-process fallback when Redis is down
_memory_store: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def store_product_context(session_id: str, context: dict[str, Any]) -> None:
    """
    Persist product context for a testing session.

    ``session_id`` is typically the WhatsApp user ID or a UUID from the
    testing portal. The context is a plain dict (JSON-serialisable subset
    of the scan response) enriched with a ``stored_at`` timestamp so the
    agent can tell the user how fresh the data is.
    """
    context["stored_at"] = datetime.utcnow().isoformat()
    key = f"{_CTX_PREFIX}:{session_id}"

    try:
        client = await _get_redis()
        await client.setex(key, _CTX_TTL_S, json.dumps(context, default=str))
        logger.info("product_context.stored | session=%r key=%s", session_id, key)
    except Exception as exc:
        logger.warning("product_context.store | redis unavailable (%s) — using memory", exc)
        _memory_store[key] = context
        # Evict oldest if cache is full
        if len(_memory_store) > _MAX_MEMORY:
            oldest = next(iter(_memory_store))
            del _memory_store[oldest]


async def get_product_context(session_id: str) -> dict[str, Any] | None:
    """
    Retrieve the stored product context for a session, or None if not found.
    """
    key = f"{_CTX_PREFIX}:{session_id}"

    try:
        client = await _get_redis()
        raw = await client.get(key)
        if raw:
            ctx = json.loads(raw)
            logger.info("product_context.hit | session=%r source=redis stored_at=%s", session_id, ctx.get("stored_at"))
            return ctx
        logger.debug("product_context.redis_miss | session=%r — checking memory fallback", session_id)
    except Exception as exc:
        logger.warning("product_context.get | redis unavailable (%s) — checking memory", exc)

    # Always check memory as a secondary store — covers the case where Redis was
    # transiently unavailable during store() but recovered before get().
    mem = _memory_store.get(key)
    if mem:
        logger.info("product_context.hit | session=%r source=memory", session_id)
    return mem


async def clear_product_context(session_id: str) -> None:
    """Remove a session's product context (e.g. when a new scan is done)."""
    key = f"{_CTX_PREFIX}:{session_id}"
    try:
        client = await _get_redis()
        await client.delete(key)
    except Exception:
        _memory_store.pop(key, None)
    logger.debug("product_context.cleared | session=%r", session_id)


def build_context_from_grocery_response(
    response: Any,          # GroceryScanResponse
    session_id: str,
) -> dict[str, Any]:
    """
    Build a flat context dict from a GroceryScanResponse.

    Flattens the Pydantic response into a plain dict optimised for LLM
    consumption: concise field names, human-readable values, no nested
    Pydantic objects that would confuse the system prompt builder.
    """
    ext = response.product_extraction
    nutrition = ext.nutrition if ext else None

    ctx: dict[str, Any] = {
        "session_id": session_id,
        "scan_type": "grocery",
        "risk_band": response.risk_band,
        "expiry_status": response.expiry_status,
    }

    # Product identity from Gemini extraction
    if ext:
        ctx["brand_name"] = ext.brand_name
        ctx["product_name"] = ext.product_name
        ctx["product_type"] = ext.product_type
        ctx["manufacturer"] = ext.manufacturer
        ctx["net_weight"] = ext.net_weight
        ctx["serving_size"] = ext.serving_size
        ctx["certifications"] = ext.certifications
        ctx["is_vegetarian"] = ext.is_vegetarian
        ctx["is_vegan"] = ext.is_vegan
        ctx["is_gluten_free"] = ext.is_gluten_free
        ctx["contains_added_sugar"] = ext.contains_added_sugar
        ctx["contains_preservatives"] = ext.contains_preservatives
        ctx["contains_artificial_colours"] = ext.contains_artificial_colours

    # Ingredients
    ctx["ingredients"] = response.ingredients or []
    ctx["ingredients_count"] = response.ingredients_count

    # Nutrition (per 100g)
    if nutrition:
        ctx["nutrition_per_100g"] = {
            "calories_kcal": nutrition.calories_kcal,
            "protein_g": nutrition.protein_g,
            "total_fat_g": nutrition.total_fat_g,
            "saturated_fat_g": nutrition.saturated_fat_g,
            "carbohydrates_g": nutrition.carbohydrates_g,
            "sugar_g": nutrition.sugar_g,
            "dietary_fiber_g": nutrition.dietary_fiber_g,
            "sodium_mg": nutrition.sodium_mg,
        }

    # Positives / negatives from Gemini analysis
    if ext:
        ctx["positives"] = ext.positives
        ctx["negatives"] = ext.negatives
        ctx["allergens_declared"] = ext.allergens_declared
        ctx["e_codes_found"] = ext.e_codes_found

    # Allergen warnings from user profile cross-check
    ctx["allergen_warnings"] = response.allergen_warnings

    # Storage
    ctx["storage_warnings"] = [
        {"condition": w.condition, "message": w.message}
        for w in (response.storage_warnings or [])
    ]

    # FSSAI
    if response.fssai:
        ctx["fssai"] = {
            "license_number": response.fssai.license_number,
            "format_valid": response.fssai.format_valid,
            "online_status": response.fssai.online_status,
        }

    # Findings summary
    ctx["findings"] = [
        {"code": f.code, "severity": f.severity, "message": f.message}
        for f in (response.findings or [])
    ]

    ctx["notes"] = response.notes or []
    ctx["dates"] = response.dates or {}

    logger.debug(
        "product_context.built | session=%r brand=%r ingredients=%s",
        session_id, ctx.get("brand_name"), ctx.get("ingredients_count"),
    )
    return ctx


def build_context_from_medicine_response(
    response: Any,   # MedicineScanResponse
    session_id: str,
) -> dict[str, Any]:
    """Build a flat context dict from a MedicineScanResponse."""
    batch = response.batch_info
    return {
        "session_id": session_id,
        "scan_type": "medicine",
        "verdict": response.verdict,
        "verdict_score": response.verdict_score,
        "verdict_summary": response.verdict_summary,
        "brand_name": response.brand_name,
        "generic_name": response.generic_name,
        "manufacturer_name": response.manufacturer_name,
        "expiry_status": response.expiry_status,
        "batch_info": {
            "batch_number": batch.batch_number,
            "expiry_date": str(batch.expiry_date) if batch and batch.expiry_date else None,
            "is_expired": batch.is_expired if batch else None,
        } if batch else None,
        "storage_warnings": [
            {"condition": w.condition, "message": w.message}
            for w in (response.storage_warnings or [])
        ],
        "notes": response.notes or [],
    }


# ---------------------------------------------------------------------------
# Redis client (reuses session_service pattern)
# ---------------------------------------------------------------------------

_redis_client = None


async def _get_redis():
    """Lazily return the shared async Redis client."""
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis
        from app.core.config import get_settings
        _redis_client = aioredis.from_url(
            get_settings().redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client
