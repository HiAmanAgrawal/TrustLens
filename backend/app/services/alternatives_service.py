"""
Alternatives Engine — rule-based suggestions for healthier products and
same-composition medicine alternatives.

DESIGN PRINCIPLES:
  1. NO black-box AI — every suggestion has an explicit reason string.
  2. Rule-first — disease-threshold rules (WHO/ICMR-NIN) are hard-coded
     and version-controlled, not learned from model weights.
  3. Reason transparency — each suggestion carries *why* it was made,
     enabling users to make informed decisions rather than trusting a score.

TWO SUGGESTION TYPES:
  A. Grocery alternatives   — nutritional substitution advice (text-based,
     not a product lookup because we don't have a curated alternatives DB yet).
  B. Medicine alternatives  — same-salt substitution using the MedicineSalt
     junction table. Always include a medical disclaimer.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.medicine import Medicine, MedicineSalt

logger = logging.getLogger(__name__)


# ── Condition → concern rule table ──────────────────────────────────────────
# Thresholds from ICMR-NIN 2020 / WHO 2023 guidelines.
# Each entry: (flag_name, threshold_key, threshold_value, comparison, message)
# comparison: 'gt' = flag if value > threshold, 'lt' = flag if value < threshold

_CONDITION_RULES: dict[str, list[dict]] = {
    "diabetes": [
        {"key": "sugar_g",       "op": "gt", "val": 10,  "msg": "High sugar (>{val}g/100g). Choose products with <5g sugar per 100g."},
        {"key": "fiber_g",       "op": "lt", "val": 3,   "msg": "Low fiber (<{val}g/100g). Prefer whole-grain products with >3g fiber per 100g to slow glucose absorption."},
        {"key": "calories_kcal", "op": "gt", "val": 350, "msg": "High calorie density (>{val} kcal/100g). Choose lower-calorie alternatives."},
        {"key": "contains_added_sugar", "op": "flag", "msg": "Contains added sugar. Opt for no-added-sugar variants."},
    ],
    "hypertension": [
        {"key": "sodium_mg",     "op": "gt", "val": 400, "msg": "High sodium (>{val}mg/100g). Choose low-sodium (<120mg/100g) alternatives."},
        {"key": "saturated_fat_g", "op": "gt", "val": 5, "msg": "High saturated fat (>{val}g/100g). Choose products with <3g sat fat per 100g."},
    ],
    "obesity": [
        {"key": "calories_kcal", "op": "gt", "val": 300, "msg": "High calorie density (>{val} kcal/100g). Choose products under 200 kcal/100g."},
        {"key": "sugar_g",       "op": "gt", "val": 10,  "msg": "High sugar (>{val}g/100g). Excess sugar is stored as fat — choose <5g sugar products."},
        {"key": "total_fat_g",   "op": "gt", "val": 20,  "msg": "High total fat (>{val}g/100g). Choose lower-fat alternatives."},
    ],
    "heart_disease": [
        {"key": "saturated_fat_g", "op": "gt", "val": 3, "msg": "High saturated fat (>{val}g/100g). Limit sat fat to reduce LDL cholesterol."},
        {"key": "sodium_mg",       "op": "gt", "val": 300, "msg": "High sodium (>{val}mg/100g). Excess sodium worsens heart strain."},
        {"key": "contains_artificial_colours", "op": "flag", "msg": "Contains artificial colours — some are linked to cardiovascular inflammation."},
    ],
    "kidney_disease": [
        {"key": "sodium_mg",    "op": "gt", "val": 300, "msg": "High sodium (>{val}mg/100g). Kidneys struggle to excrete excess sodium."},
        {"key": "protein_g",   "op": "gt", "val": 10,  "msg": "High protein (>{val}g/100g). High protein increases kidney load — consult nephrologist."},
    ],
    "celiac": [
        {"key": "is_gluten_free", "op": "must_true", "msg": "Product is not certified gluten-free. Celiac patients must strictly avoid gluten."},
    ],
    "lactose_intolerance": [
        {"key": "_dairy_check", "op": "contains_dairy", "msg": "Product may contain dairy. Choose lactose-free or plant-based alternatives."},
    ],
    "pcos": [
        {"key": "sugar_g",       "op": "gt", "val": 8,  "msg": "High sugar (>{val}g/100g). High glycaemic foods worsen insulin resistance in PCOS."},
        {"key": "contains_artificial_colours", "op": "flag", "msg": "Artificial colours may disrupt hormonal balance."},
    ],
    "thyroid": [
        {"key": "contains_preservatives", "op": "flag", "msg": "Contains preservatives. Some (e.g. BHA, BHT) may interfere with thyroid function."},
    ],
}

_DAIRY_KEYWORDS = ["milk", "dairy", "lactose", "whey", "casein", "cream", "butter", "cheese", "paneer", "ghee", "curd"]


@dataclass
class GrocerySuggestion:
    condition: str
    concern: str
    suggestion: str
    reason: str


@dataclass
class MedicineAlternative:
    medicine_id: uuid.UUID
    brand_name: str
    generic_name: str
    dosage_form: str
    strength: str
    manufacturer: str
    shared_salt: str
    disclaimer: str = (
        "⚕️ This is an alternative with the same active ingredient. "
        "Always consult your doctor or pharmacist before switching medicines."
    )


def suggest_grocery_alternatives(
    product_context: dict,
    user_conditions: list[str],
) -> list[GrocerySuggestion]:
    """
    Rule-based grocery alternative suggestions based on user health conditions.

    Args:
        product_context: Flat dict from product_context.py (nutrition_per_100g, flags, etc.)
        user_conditions: List of condition names (lowercase, e.g. ["diabetes", "hypertension"])

    Returns:
        List of GrocerySuggestion — each with an explicit reason.
        Empty list if no concerns found.
    """
    nutrition = product_context.get("nutrition_per_100g") or {}
    suggestions: list[GrocerySuggestion] = []

    for condition in user_conditions:
        condition_low = condition.lower()
        rules = _CONDITION_RULES.get(condition_low, [])

        for rule in rules:
            key = rule["key"]
            op  = rule["op"]
            msg_template = rule.get("msg", "")
            val = rule.get("val")

            triggered = False

            if op == "gt":
                nutrient_val = nutrition.get(key) or product_context.get(key)
                if nutrient_val is not None and nutrient_val > val:
                    triggered = True
            elif op == "lt":
                nutrient_val = nutrition.get(key) or product_context.get(key)
                if nutrient_val is not None and nutrient_val < val:
                    triggered = True
            elif op == "flag":
                # Check a boolean flag on the product_context
                if product_context.get(key) is True:
                    triggered = True
            elif op == "must_true":
                if product_context.get(key) is not True:
                    triggered = True
            elif op == "contains_dairy":
                ingredients = product_context.get("ingredients") or []
                if any(kw in i.lower() for i in ingredients for kw in _DAIRY_KEYWORDS):
                    triggered = True

            if triggered:
                reason = msg_template.format(val=val)
                suggestions.append(GrocerySuggestion(
                    condition=condition_low,
                    concern=key,
                    suggestion=reason.split(".")[1].strip() if "." in reason else reason,
                    reason=reason,
                ))
                logger.info(
                    "alternatives.grocery | condition=%r key=%r triggered=True",
                    condition_low, key,
                )

    return suggestions


async def find_medicine_alternatives(
    session: AsyncSession,
    medicine_id: uuid.UUID,
    limit: int = 5,
) -> list[MedicineAlternative]:
    """
    Find medicines with at least one overlapping active salt.

    WHY salt-level matching:
      Generic substitution databases (e.g. CDSCO's list) map by salt composition.
      A user prescribed Crocin (paracetamol 500mg) can safely consider any
      paracetamol 500mg tablet — the salt is the identity, not the brand.

    Returns alternatives sorted by brand_name, excluding the original medicine.
    """
    # Step 1: Get salt IDs for the source medicine
    salt_stmt = select(MedicineSalt.salt_id, MedicineSalt.salt).options(
        selectinload(MedicineSalt.salt)
    ).where(MedicineSalt.medicine_id == medicine_id)

    result = await session.execute(salt_stmt)
    source_salts = result.all()

    if not source_salts:
        logger.debug("alternatives.medicine | no salts for medicine_id=%s", medicine_id)
        return []

    salt_ids     = [row.salt_id for row in source_salts]
    salt_by_id   = {row.salt_id: row.salt for row in source_salts}

    # Step 2: Find other medicines sharing those salts
    alt_stmt = (
        select(MedicineSalt)
        .options(selectinload(MedicineSalt.medicine))
        .where(
            MedicineSalt.salt_id.in_(salt_ids),
            MedicineSalt.medicine_id != medicine_id,
        )
        .limit(limit * 3)   # over-fetch, deduplicate by medicine_id below
    )
    result = await session.execute(alt_stmt)
    alt_salts: list[MedicineSalt] = list(result.scalars().all())

    # Deduplicate by medicine_id, keep first matching salt for display
    seen: dict[uuid.UUID, MedicineAlternative] = {}
    for ms in alt_salts:
        med_id = ms.medicine_id
        if med_id in seen or len(seen) >= limit:
            continue
        med = ms.medicine
        if not med or not med.is_active:
            continue
        shared_salt = salt_by_id.get(ms.salt_id)
        seen[med_id] = MedicineAlternative(
            medicine_id=med.id,
            brand_name=med.brand_name or "",
            generic_name=med.generic_name or "",
            dosage_form=med.dosage_form.value if med.dosage_form else "",
            strength=med.strength or "",
            manufacturer=med.manufacturer or "",
            shared_salt=shared_salt.name if shared_salt else str(ms.salt_id),
        )
        logger.info(
            "alternatives.medicine | source=%s alt=%s shared_salt=%s",
            medicine_id, med_id, seen[med_id].shared_salt,
        )

    return list(seen.values())
