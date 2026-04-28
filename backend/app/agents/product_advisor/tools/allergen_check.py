"""
allergen_check tool — run the allergen + dietary mismatch checker against the
current product context.

WHY a separate tool (not rolled into assess_suitability):
  Allergen detection is safety-critical and must be surfaced separately so
  the LLM can distinguish "nutritionally sub-optimal" (assess_suitability)
  from "may cause anaphylaxis" (allergen_check). The two tools serve
  different urgency levels.
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def allergen_check(ingredients_json: str, user_allergens_json: str, dietary_preference: str = "") -> str:
    """
    Check product ingredients against a user's allergen profile and dietary preference.

    Use this when the user asks:
    - "Am I allergic to anything in this?"
    - "Does this contain nuts / gluten / dairy?"
    - "Is this safe for a vegan / vegetarian / halal diet?"
    - "Does this product suit my diet?"

    Args:
        ingredients_json:    JSON array of ingredient strings from the product label.
                             Use the `ingredients` field from product context.
                             Example: '["wheat flour", "skimmed milk", "sugar"]'

        user_allergens_json: JSON array of allergen category strings the user is
                             allergic to. Use AllergenCategoryEnum values:
                             gluten, milk, peanuts, tree_nuts, eggs, fish,
                             crustaceans, molluscs, soybeans, sesame, mustard,
                             sulphites, celery, lupin, coconut, corn, latex.
                             Example: '["gluten", "milk"]'
                             Pass '[]' if the user has no known allergens.

        dietary_preference:  User's dietary preference string. Supported values:
                             vegetarian, jain, vegan, gluten_free, halal.
                             Pass empty string if no preference.

    Returns:
        A summary of detected allergen warnings and dietary mismatches.
        Empty result means no conflicts found.
    """
    logger.info(
        "tool.allergen_check | diet=%r allergens=%s",
        dietary_preference, user_allergens_json[:80],
    )

    try:
        ingredients: list[str] = json.loads(ingredients_json) if ingredients_json else []
    except Exception:
        ingredients = []

    try:
        user_allergens: list[str] = json.loads(user_allergens_json) if user_allergens_json else []
    except Exception:
        user_allergens = []

    from app.services.allergen_service import run_full_check

    result = run_full_check(
        ingredients=ingredients,
        user_allergen_categories=user_allergens,
        user_allergen_names=None,
        dietary_preference=dietary_preference or None,
    )

    if not result.has_issues:
        return (
            "✅ No allergen conflicts or dietary mismatches detected based on the ingredients list.\n\n"
            "⚠️ Note: This check is based on keyword matching of the label text. "
            "Always check the physical label for 'may contain' traces."
        )

    lines: list[str] = []

    if result.allergen_warnings:
        lines.append("🚨 ALLERGEN WARNINGS:")
        for w in result.allergen_warnings:
            matched_str = ", ".join(w.matched_ingredients[:3])
            lines.append(f"  • {w.allergen.upper()}: found in → {matched_str}")
            lines.append(f"    {w.severity_note}")
        lines.append("")

    if result.diet_mismatches:
        lines.append("🥗 DIETARY MISMATCHES:")
        for m in result.diet_mismatches:
            lines.append(f"  • {m.reason}")
        lines.append("")

    lines.append(
        "⚕️ Always verify with the physical product label. "
        "For severe allergies, contact the manufacturer to confirm manufacturing practices."
    )

    logger.info(
        "tool.allergen_check | warnings=%d mismatches=%d",
        len(result.allergen_warnings), len(result.diet_mismatches),
    )
    return "\n".join(lines)
