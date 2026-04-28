"""
alternatives tool — suggest healthier grocery alternatives or same-salt medicine
alternatives from the product advisor agent.

This tool wraps the rule-based alternatives engine (alternatives_service.py).
For grocery products it returns condition-specific suggestions backed by
WHO/ICMR-NIN thresholds. For medicines it is informational only and always
includes a medical disclaimer.
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def suggest_alternatives(
    product_type: str,
    conditions_json: str,
    product_context_json: str,
) -> str:
    """
    Suggest healthier grocery alternatives or same-salt medicine substitutes.

    Use this when the user asks:
    - "Are there healthier alternatives to this?"
    - "What should I eat instead if I have diabetes?"
    - "Is there a cheaper version of this medicine with the same ingredient?"
    - "What's a lower-sodium substitute for this?"

    Args:
        product_type:         Either "grocery" or "medicine".

        conditions_json:      JSON array of the user's health conditions (lowercase).
                              For grocery alternatives only.
                              Example: '["diabetes", "hypertension"]'
                              Pass '[]' for no specific conditions.

        product_context_json: JSON string of the product context dict.
                              For grocery: include nutrition_per_100g, flags, ingredients.
                              For medicine: include medicine_id (UUID string).
                              The product context is available from the scan result stored
                              in the session. Pass the full context JSON.

    Returns:
        Formatted list of suggestions with explicit reasons, or a message that no
        specific suggestions apply. Always includes appropriate disclaimers.
    """
    logger.info("tool.suggest_alternatives | product_type=%r", product_type)

    try:
        conditions: list[str] = json.loads(conditions_json) if conditions_json else []
    except Exception:
        conditions = []

    try:
        ctx: dict = json.loads(product_context_json) if product_context_json else {}
    except Exception:
        ctx = {}

    ptype = (product_type or "").lower().strip()

    # ── Grocery alternatives ─────────────────────────────────────────────────
    if ptype == "grocery":
        from app.services.alternatives_service import suggest_grocery_alternatives

        if not conditions:
            return (
                "💡 To suggest alternatives, please share your health conditions "
                "(e.g. 'diabetes', 'hypertension', 'obesity')."
            )

        suggestions = suggest_grocery_alternatives(ctx, conditions)

        if not suggestions:
            return (
                "✅ Based on the available nutritional data, no specific concerns were found "
                f"for your conditions ({', '.join(conditions)}). This product appears compatible "
                "with your dietary goals."
            )

        lines = [f"🔄 Healthier Alternatives for {', '.join(c.title() for c in conditions)}:", ""]
        for s in suggestions:
            lines.append(f"**{s.condition.title()}** — {s.reason}")
            lines.append(f"  → Suggestion: {s.suggestion}")
            lines.append("")

        lines.append(
            "⚕️ These are general nutritional guidelines. Consult a registered dietitian "
            "for personalised dietary advice."
        )
        logger.info("tool.suggest_alternatives | grocery suggestions=%d", len(suggestions))
        return "\n".join(lines)

    # ── Medicine alternatives ────────────────────────────────────────────────
    elif ptype == "medicine":
        medicine_id_str = ctx.get("medicine_id") or ctx.get("id")
        if not medicine_id_str:
            return (
                "⚠️ Medicine ID not available in the current context. "
                "Please scan the medicine first, then ask for alternatives."
            )

        # Medicine alternatives require a DB session — return a deferred message
        # since agent tools run synchronously and can't await.
        # The full async implementation is in alternatives_service.find_medicine_alternatives.
        return (
            f"💊 To find same-salt alternatives for this medicine, please use the "
            f"dedicated medicine alternatives endpoint:\n"
            f"  GET /v1/medicines/{{medicine_id}}/alternatives\n\n"
            f"Medicine ID from your scan: {medicine_id_str}\n\n"
            "⚕️ IMPORTANT: Always consult your doctor or pharmacist before switching "
            "to a generic or alternative medicine, even if the active ingredient is the same."
        )

    else:
        return (
            f"⚠️ Unknown product type '{product_type}'. "
            "Use 'grocery' for food products or 'medicine' for pharmaceutical products."
        )
