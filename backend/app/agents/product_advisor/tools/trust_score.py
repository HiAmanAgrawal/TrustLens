"""
calculate_trust_score tool — deterministic product trustworthiness score.

Computes a 0–100 score from verifiable label attributes:
  - FSSAI license (valid / invalid / missing)
  - Ingredient transparency (count known / unknown)
  - Expiry status
  - Certification presence
  - Concerning additives (E-codes)

WHY deterministic: Users deserve a reproducible score, not an LLM opinion.
  The LLM can then *explain* the score, but the number itself is rule-based.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def calculate_trust_score(context_json: str) -> str:
    """
    Calculate a deterministic trust/quality score (0–100) for a scanned product.

    Use this when the user asks:
    - "How trustworthy is this product?"
    - "Give me an overall score for this product"
    - "Is this a quality product?"

    Args:
        context_json: JSON string of the product context (pass the full
                      product_context dict as a JSON string).

    Returns:
        A score breakdown showing what added and deducted points.
    """
    import json as _json

    logger.info("tool.calculate_trust_score | computing score")

    try:
        ctx = _json.loads(context_json) if context_json else {}
    except Exception:
        ctx = {}

    score = 50      # neutral baseline
    breakdown: list[str] = []

    # ── FSSAI (+20 / -15 / -10) ─────────────────────────────────────────────
    fssai = ctx.get("fssai") or {}
    fssai_status = fssai.get("online_status", "skipped")
    if fssai_status == "valid":
        score += 20
        breakdown.append("+20: FSSAI license verified online")
    elif fssai.get("format_valid") is True:
        score += 8
        breakdown.append("+8: FSSAI license format valid (online check unavailable)")
    elif fssai_status == "invalid":
        score -= 15
        breakdown.append("-15: FSSAI license invalid")
    elif not ctx.get("fssai"):
        score -= 10
        breakdown.append("-10: No FSSAI license found on label")

    # ── Ingredients transparency (+10 / -5 / -10) ───────────────────────────
    ing_count = ctx.get("ingredients_count")
    if ing_count is not None:
        score += 10
        breakdown.append(f"+10: Ingredients fully listed ({ing_count} items)")
    else:
        score -= 5
        breakdown.append("-5: Ingredients list not readable")

    e_codes = ctx.get("e_codes_found") or []
    if len(e_codes) > 3:
        score -= 10
        breakdown.append(f"-10: Many concerning additives ({', '.join(e_codes[:4])}…)")
    elif e_codes:
        score -= 4
        breakdown.append(f"-4: Some E-codes present ({', '.join(e_codes)})")

    # ── Certifications (+5 each, max +15) ───────────────────────────────────
    certs = ctx.get("certifications") or []
    cert_bonus = min(len(certs) * 5, 15)
    if cert_bonus:
        score += cert_bonus
        breakdown.append(f"+{cert_bonus}: Certifications ({', '.join(certs[:3])})")

    # ── Expiry status (+5 / -20 / 0) ────────────────────────────────────────
    exp = ctx.get("expiry_status", "UNKNOWN")
    if exp == "SAFE":
        score += 5
        breakdown.append("+5: Not expired")
    elif exp == "NEAR_EXPIRY":
        score -= 5
        breakdown.append("-5: Near expiry — use soon")
    elif exp == "EXPIRED":
        score -= 20
        breakdown.append("-20: EXPIRED — do not consume")

    # ── Nutrition concerns (-5 each) ─────────────────────────────────────────
    neg_count = len(ctx.get("negatives") or [])
    if neg_count > 0:
        deduct = min(neg_count * 5, 15)
        score -= deduct
        breakdown.append(f"-{deduct}: {neg_count} nutritional concern(s)")

    pos_count = len(ctx.get("positives") or [])
    if pos_count > 0:
        add = min(pos_count * 3, 9)
        score += add
        breakdown.append(f"+{add}: {pos_count} positive nutritional attribute(s)")

    # ── Risk band override ───────────────────────────────────────────────────
    risk = ctx.get("risk_band", "unknown")
    if risk == "high":
        score = min(score, 40)
        breakdown.append("(capped at 40 — high risk band)")
    elif risk == "medium":
        score = min(score, 70)

    score = max(0, min(100, score))

    # ── Verdict label ────────────────────────────────────────────────────────
    if score >= 80:
        label = "EXCELLENT"
    elif score >= 65:
        label = "GOOD"
    elif score >= 50:
        label = "MODERATE"
    elif score >= 35:
        label = "POOR"
    else:
        label = "VERY POOR"

    product_name = ctx.get("product_name") or ctx.get("brand_name") or "this product"

    lines = [
        f"📊 Trust Score for **{product_name}**: **{score}/100** ({label})",
        "",
        "Breakdown:",
    ] + [f"  {item}" for item in breakdown] + [
        "",
        "Score is based on FSSAI license, ingredient transparency, certifications, "
        "expiry status, and nutrition data. It is NOT a safety certification.",
    ]

    logger.info("tool.calculate_trust_score | score=%d label=%s", score, label)
    return "\n".join(lines)
