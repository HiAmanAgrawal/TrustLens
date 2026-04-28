"""
assess_suitability tool — rule-based dietary/health suitability check.

Answers questions like:
  - "Can I eat this if I have diabetes?"
  - "Is this safe during pregnancy?"
  - "How often can a child eat this?"

WHY rule-based (not LLM-only):
  These checks use fixed thresholds from established dietary guidelines
  (ICMR-NIN, WHO, FSSAI) so they are reproducible and not subject to LLM
  hallucination. The LLM uses this output as grounded evidence, not as a
  medical diagnosis.

IMPORTANT: Output is informational only. Always directs users to a healthcare
  professional for medical decisions.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dietary thresholds (per-100g unless noted)
# WHO / ICMR-NIN 2020 reference values
# ---------------------------------------------------------------------------
_THRESHOLDS = {
    "sugar_high":         10.0,    # g/100g — above this = high sugar
    "sodium_high":       400.0,    # mg/100g — above this = high sodium
    "sat_fat_high":        5.0,    # g/100g — above this = high sat fat
    "calories_high":     400.0,    # kcal/100g — energy-dense snack
    "fiber_good":          3.0,    # g/100g — at least this = good fiber
    "protein_good":        5.0,    # g/100g — at least this = good protein
    # Daily limits (total diet, not per product)
    "daily_sugar_g":      25.0,    # WHO free-sugar limit
    "daily_sodium_mg":  2300.0,    # WHO sodium limit
    "daily_sat_fat_g":    20.0,    # ~10% of 2000 kcal diet
}

# Condition-specific rules:
#   condition → list of (check_fn(nutrition, ext) → str | None)
# Return None if no issue; return warning string if a concern applies.

def _rules_for(condition: str, nutrition: dict, ext: dict) -> list[str]:
    """Return a list of concern strings for a given health condition."""
    condition_lower = condition.lower().strip()
    concerns: list[str] = []
    positives: list[str] = []

    sugar_g = nutrition.get("sugar_g")
    sodium_mg = nutrition.get("sodium_mg")
    sat_fat_g = nutrition.get("saturated_fat_g")
    calories = nutrition.get("calories_kcal")
    fiber_g = nutrition.get("dietary_fiber_g")
    protein_g = nutrition.get("protein_g")
    contains_added_sugar = ext.get("contains_added_sugar")
    contains_preservatives = ext.get("contains_preservatives")
    is_gluten_free = ext.get("is_gluten_free")

    # ── Diabetes / Blood sugar ───────────────────────────────────────────────
    if any(kw in condition_lower for kw in ("diabet", "sugar", "blood sugar", "hyperglycemia")):
        if sugar_g is not None and sugar_g > _THRESHOLDS["sugar_high"]:
            concerns.append(
                f"HIGH SUGAR: {sugar_g}g per 100g (limit is {_THRESHOLDS['sugar_high']}g/100g "
                f"for frequent consumption). Occasional small portions only."
            )
        if contains_added_sugar:
            concerns.append("Contains added sugar — check portion size carefully.")
        if fiber_g is not None and fiber_g >= _THRESHOLDS["fiber_good"]:
            positives.append(f"Good dietary fiber ({fiber_g}g/100g) which slows glucose absorption.")
        if not concerns:
            positives.append("Sugar content appears acceptable for moderate consumption.")

    # ── Hypertension / Blood pressure / Heart ───────────────────────────────
    elif any(kw in condition_lower for kw in ("hypert", "blood pressure", "bp", "heart", "cardiac")):
        if sodium_mg is not None and sodium_mg > _THRESHOLDS["sodium_high"]:
            concerns.append(
                f"HIGH SODIUM: {sodium_mg}mg per 100g. Daily limit is 2300mg total. "
                f"This product alone provides {sodium_mg/23:.0f}% of daily sodium."
            )
        if sat_fat_g is not None and sat_fat_g > _THRESHOLDS["sat_fat_high"]:
            concerns.append(
                f"HIGH SATURATED FAT: {sat_fat_g}g/100g. Limit to ≤5g/100g for heart health."
            )
        if not concerns:
            positives.append("Sodium and saturated fat levels appear heart-friendly.")

    # ── Obesity / Weight management ──────────────────────────────────────────
    elif any(kw in condition_lower for kw in ("obes", "weight", "overweight", "diet")):
        if calories is not None and calories > _THRESHOLDS["calories_high"]:
            concerns.append(
                f"CALORIE-DENSE: {calories}kcal per 100g. Limit portion size carefully."
            )
        if sugar_g is not None and sugar_g > _THRESHOLDS["sugar_high"]:
            concerns.append(f"High sugar ({sugar_g}g/100g) can contribute to weight gain.")
        if fiber_g is not None and fiber_g >= _THRESHOLDS["fiber_good"]:
            positives.append(f"Fiber ({fiber_g}g/100g) promotes satiety.")
        if protein_g is not None and protein_g >= _THRESHOLDS["protein_good"]:
            positives.append(f"Protein ({protein_g}g/100g) supports muscle and satiety.")

    # ── Celiac / Gluten intolerance ──────────────────────────────────────────
    elif any(kw in condition_lower for kw in ("celiac", "gluten", "coeliac")):
        if is_gluten_free is True:
            positives.append("Marked gluten-free on label.")
        elif is_gluten_free is False:
            concerns.append("NOT gluten-free — contains gluten ingredients.")
        else:
            concerns.append(
                "Gluten-free status unclear from label. Check for wheat, barley, rye, oats."
            )

    # ── Lactose intolerance / Milk allergy ───────────────────────────────────
    elif any(kw in condition_lower for kw in ("lactose", "milk allerg", "dairy")):
        allergens = ext.get("allergens_declared") or []
        ing = [i.lower() for i in (ext.get("ingredients") or [])]
        milk_kws = ("milk", "dairy", "lactose", "whey", "casein", "cream", "butter", "cheese")
        has_milk = any(kw in a.lower() for a in allergens for kw in milk_kws) or \
                   any(kw in i for i in ing for kw in milk_kws)
        if has_milk:
            concerns.append("Contains milk/dairy — not suitable for lactose intolerance or milk allergy.")
        else:
            positives.append("No obvious milk/dairy ingredients detected.")

    # ── Pregnancy ────────────────────────────────────────────────────────────
    elif "pregnan" in condition_lower:
        if contains_preservatives:
            concerns.append(
                "Contains preservatives — consult your doctor about specific additives during pregnancy."
            )
        if sodium_mg is not None and sodium_mg > _THRESHOLDS["sodium_high"]:
            concerns.append(f"High sodium ({sodium_mg}mg/100g) — monitor intake during pregnancy.")
        concerns.append(
            "⚕️ Always consult your gynaecologist/dietitian for dietary advice during pregnancy."
        )

    # ── Child / Kids ─────────────────────────────────────────────────────────
    elif any(kw in condition_lower for kw in ("child", "kid", "toddler", "infant", "baby")):
        if sugar_g is not None and sugar_g > 5.0:
            concerns.append(
                f"SUGAR: {sugar_g}g/100g. WHO recommends children have less than 25g free sugar/day — "
                f"a 30g serving of this provides {sugar_g * 0.3:.1f}g."
            )
        if sodium_mg is not None and sodium_mg > 300.0:
            concerns.append(
                f"HIGH SODIUM for children: {sodium_mg}mg/100g. "
                f"Children under 5 need less than 1000mg/day."
            )
        e_codes = ext.get("e_codes_found") or []
        if e_codes:
            concerns.append(
                f"Contains E-codes {', '.join(e_codes)} — some artificial colours/preservatives "
                f"linked to hyperactivity in children."
            )

    # ── General / no specific condition ─────────────────────────────────────
    else:
        if sugar_g is not None and sugar_g > _THRESHOLDS["sugar_high"]:
            concerns.append(f"Sugar: {sugar_g}g/100g — higher than recommended for daily snacking.")
        if sodium_mg is not None and sodium_mg > _THRESHOLDS["sodium_high"]:
            concerns.append(f"Sodium: {sodium_mg}mg/100g — moderate your intake.")
        positives.extend(ext.get("positives") or [])

    return concerns, positives


@tool
def assess_suitability(condition: str, nutrition_json: str) -> str:
    """
    Assess whether the scanned product is suitable for someone with a specific
    health condition or dietary requirement.

    Use this tool when the user asks:
    - "Can I eat this if I have diabetes?"
    - "Is this ok for my child?"
    - "Is this suitable for someone trying to lose weight?"
    - "Should I avoid this if I have high blood pressure?"

    Args:
        condition:      Health condition or dietary requirement (free text, e.g.
                        "diabetes", "hypertension", "celiac disease", "pregnancy",
                        "child under 5").
        nutrition_json: JSON string with nutrition values (use the product_context
                        nutrition_per_100g field). Must have keys like sugar_g,
                        sodium_mg, etc. Pass "{}" if not available.

    Returns:
        A structured suitability assessment with specific concerns and positives.
        Always includes a disclaimer that this is informational, not medical advice.
    """
    import json as _json

    logger.info("tool.assess_suitability | condition=%r", condition)

    try:
        nutrition = _json.loads(nutrition_json) if nutrition_json else {}
    except Exception:
        nutrition = {}

    # ext is passed as part of the tool context via the parent call; since tool
    # can't directly access state, we pass a separate simplified ext dict
    ext: dict[str, Any] = {}

    concerns, positives = _rules_for(condition, nutrition, ext)

    lines: list[str] = [f"🏥 Suitability Assessment for: **{condition}**", ""]

    if positives:
        lines.append("✅ Positive aspects:")
        for p in positives:
            lines.append(f"  • {p}")
        lines.append("")

    if concerns:
        lines.append("⚠️ Concerns:")
        for c in concerns:
            lines.append(f"  • {c}")
    else:
        lines.append("✅ No major concerns detected based on available nutrition data.")

    lines.append("")
    lines.append(
        "⚕️ Disclaimer: This is informational only based on label data. "
        "Consult a registered dietitian or doctor before making dietary changes."
    )

    result = "\n".join(lines)
    logger.info(
        "tool.assess_suitability | concerns=%d positives=%d",
        len(concerns), len(positives),
    )
    return result
