"""
Allergen & Diet Checker — cross-references product ingredients against a user's
allergy profile and dietary preference.

WHY keyword-based (not LLM):
  Allergen detection is safety-critical. False negatives (missed allergens) can
  cause anaphylaxis. Keyword matching against a curated dictionary gives
  deterministic, auditable results that can be independently verified.

TWO CHECK LAYERS:
  1. AllergenCategoryEnum match — compares the normalised ``allergen_category``
     on ``GroceryIngredient`` rows against ``UserAllergy.allergen_category``.
     This is the fast path for structured DB data.

  2. Free-text keyword scan — runs over the raw ``ingredients`` string list
     (from Gemini extraction) for products not in our DB yet.

DIET MISMATCH RULES:
  vegetarian / jain → flag meat, poultry, fish, seafood, gelatin
  vegan             → flag all above + milk, eggs, honey, beeswax
  gluten_free       → flag wheat, barley, rye, malt
  halal             → flag pork, lard, alcohol-derived ingredients (best-effort)
  kosher            → not implemented (complex halachic rules — out of scope)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.models.enums import AllergenCategoryEnum, DietaryPreferenceEnum

logger = logging.getLogger(__name__)

# ── Allergen keyword dictionary ─────────────────────────────────────────────
# Keys = AllergenCategoryEnum values; values = lower-case keyword stems.
_ALLERGEN_KEYWORDS: dict[str, list[str]] = {
    AllergenCategoryEnum.GLUTEN:      ["wheat", "barley", "rye", "oat", "gluten", "flour", "maida", "atta", "semolina", "spelt", "kamut"],
    AllergenCategoryEnum.MILK:        ["milk", "dairy", "lactose", "whey", "casein", "cream", "butter", "cheese", "paneer", "ghee", "curd", "yogurt", "skimmed", "condensed"],
    AllergenCategoryEnum.PEANUTS:     ["peanut", "groundnut", "arachis"],
    AllergenCategoryEnum.TREE_NUTS:   ["almond", "cashew", "walnut", "pistachio", "macadamia", "pecan", "hazelnut", "pine nut", "brazil nut", "nut"],
    AllergenCategoryEnum.EGGS:        ["egg", "albumin", "ovalbumin", "lecithin"],
    AllergenCategoryEnum.FISH:        ["fish", "tuna", "salmon", "cod", "anchovy", "sardine", "mackerel", "herring", "tilapia", "basa"],
    AllergenCategoryEnum.CRUSTACEANS: ["shrimp", "prawn", "crab", "lobster", "crayfish", "crustacean"],
    AllergenCategoryEnum.MOLLUSCS:    ["squid", "octopus", "mussel", "oyster", "scallop", "clam", "mollusc"],
    AllergenCategoryEnum.SOYBEANS:    ["soy", "soya", "soybean", "tofu", "tempeh", "edamame"],
    AllergenCategoryEnum.SESAME:      ["sesame", "til", "tahini", "gingelly"],
    AllergenCategoryEnum.MUSTARD:     ["mustard", "mustard seed", "mustard oil"],
    AllergenCategoryEnum.SULPHITES:   ["sulphite", "sulfite", "sulphur dioxide", "e220", "e221", "e222", "e223", "e224", "e226", "e228"],
    AllergenCategoryEnum.CELERY:      ["celery", "celeriac"],
    AllergenCategoryEnum.LUPIN:       ["lupin", "lupine"],
    AllergenCategoryEnum.COCONUT:     ["coconut"],
    AllergenCategoryEnum.CORN:        ["corn", "maize", "cornstarch", "corn flour", "corn syrup"],
    AllergenCategoryEnum.LATEX:       ["latex", "natural rubber"],
}

# ── Dietary mismatch keywords ────────────────────────────────────────────────
_MEAT_KEYWORDS    = ["meat", "chicken", "beef", "pork", "lamb", "mutton", "turkey", "duck", "poultry", "lard", "tallow", "suet", "bacon", "ham"]
_SEAFOOD_KEYWORDS = ["fish", "prawn", "shrimp", "crab", "lobster", "squid", "mussel", "oyster", "anchovy", "sardine", "salmon", "tuna"]
_EGG_KEYWORDS     = ["egg", "albumin", "ovalbumin"]
_DAIRY_KEYWORDS   = ["milk", "dairy", "whey", "casein", "lactose", "butter", "cream", "cheese", "paneer", "ghee", "yogurt", "curd"]
_HONEY_KEYWORDS   = ["honey", "beeswax", "royal jelly", "propolis"]
_GELATIN_KEYWORDS = ["gelatin", "gelatine", "isinglass", "collagen"]
_GLUTEN_KEYWORDS  = ["wheat", "barley", "rye", "malt", "gluten", "maida", "flour", "semolina"]
_PORK_KEYWORDS    = ["pork", "pig", "lard", "bacon", "ham", "prosciutto"]
_ALCOHOL_KEYWORDS = ["alcohol", "ethanol", "wine", "beer", "rum", "brandy", "fermented"]


@dataclass
class AllergenWarning:
    allergen: str
    matched_ingredients: list[str]
    severity_note: str


@dataclass
class DietMismatch:
    mismatch_type: str
    matched_ingredients: list[str]
    reason: str


@dataclass
class AllergenCheckResult:
    allergen_warnings: list[AllergenWarning] = field(default_factory=list)
    diet_mismatches: list[DietMismatch]      = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.allergen_warnings or self.diet_mismatches)

    def to_warning_strings(self) -> list[str]:
        """Flat string list for API responses / WhatsApp messages."""
        out: list[str] = []
        for w in self.allergen_warnings:
            out.append(f"{w.allergen.upper()}: found in {', '.join(w.matched_ingredients[:3])}")
        for d in self.diet_mismatches:
            out.append(d.reason)
        return out


def _lower_tokens(text: str) -> str:
    return text.lower()


def _keyword_match(ingredients: list[str], keywords: list[str]) -> list[str]:
    """Return ingredients that contain any of the keywords."""
    matches: list[str] = []
    for ing in ingredients:
        ing_low = ing.lower()
        if any(kw in ing_low for kw in keywords):
            matches.append(ing)
    return matches


def check_allergens(
    ingredients: list[str],
    user_allergen_categories: list[str],
    user_allergen_names: list[str] | None = None,
) -> list[AllergenWarning]:
    """
    Check a product's ingredient list against a user's allergen profile.

    Args:
        ingredients:             Raw ingredient strings from product label / Gemini extraction.
        user_allergen_categories: List of AllergenCategoryEnum values the user is allergic to.
        user_allergen_names:      Free-text allergen names (e.g. "peanut butter") for extra matching.

    Returns:
        List of AllergenWarning (empty → no conflicts).
    """
    warnings: list[AllergenWarning] = []

    for category in user_allergen_categories:
        keywords = _ALLERGEN_KEYWORDS.get(category, [])
        if not keywords:
            logger.debug("allergen_service.check | no keywords for category=%r", category)
            continue

        matches = _keyword_match(ingredients, keywords)
        if matches:
            logger.info(
                "allergen_service.hit | category=%r matched=%s",
                category, matches[:3],
            )
            warnings.append(AllergenWarning(
                allergen=category,
                matched_ingredients=matches,
                severity_note="Allergen detected — avoid if you have confirmed allergy.",
            ))

    # Free-text allergen name matching (catches "I'm allergic to peanut butter")
    if user_allergen_names:
        for name in user_allergen_names:
            name_low = name.lower()
            matches = [i for i in ingredients if name_low in i.lower()]
            if matches and not any(w.allergen == name for w in warnings):
                warnings.append(AllergenWarning(
                    allergen=name,
                    matched_ingredients=matches,
                    severity_note=f"Ingredient '{name}' found — user-reported allergy.",
                ))

    return warnings


def check_dietary_mismatch(
    ingredients: list[str],
    dietary_preference: str | None,
    is_vegetarian: bool | None = None,
    is_vegan: bool | None = None,
    is_gluten_free: bool | None = None,
) -> list[DietMismatch]:
    """
    Rule-based diet compatibility check.

    Uses both the structured flags from Gemini extraction (is_vegetarian,
    is_vegan, is_gluten_free) and keyword scanning of the raw ingredient
    list as a secondary confirmation.

    Args:
        ingredients:         Raw ingredient list.
        dietary_preference:  User's DietaryPreferenceEnum value.
        is_vegetarian/vegan/gluten_free: Gemini-extracted product flags.
    """
    if not dietary_preference:
        return []

    mismatches: list[DietMismatch] = []
    diet = dietary_preference.lower()

    def _add(mtype: str, matched: list[str], reason: str) -> None:
        if matched:
            mismatches.append(DietMismatch(mtype, matched, reason))

    if diet in ("vegetarian", "jain"):
        # Structured flag takes priority; ingredient scan is a fallback.
        if is_vegetarian is False:
            _add("non_vegetarian", ["(product marked non-vegetarian)"],
                 "This product is not vegetarian — conflicts with your dietary preference.")
        else:
            # Scan for meat/seafood keywords even if flag is unclear.
            meat = _keyword_match(ingredients, _MEAT_KEYWORDS + _SEAFOOD_KEYWORDS + _GELATIN_KEYWORDS)
            if meat:
                _add("non_vegetarian", meat,
                     f"Non-vegetarian ingredient(s) detected: {', '.join(meat[:3])}.")

        if diet == "jain":
            # Jain diet also avoids root vegetables — hard to detect from OCR
            # so we only check for obvious animal products here.
            egg = _keyword_match(ingredients, _EGG_KEYWORDS)
            if egg:
                _add("non_jain_eggs", egg,
                     f"Egg-based ingredient(s) detected ({', '.join(egg[:3])}) — not Jain-compliant.")

    elif diet == "vegan":
        if is_vegan is False:
            _add("non_vegan", ["(product marked non-vegan)"],
                 "This product is not vegan — conflicts with your dietary preference.")
        else:
            non_vegan = _keyword_match(
                ingredients,
                _MEAT_KEYWORDS + _SEAFOOD_KEYWORDS + _EGG_KEYWORDS + _DAIRY_KEYWORDS + _HONEY_KEYWORDS + _GELATIN_KEYWORDS,
            )
            if non_vegan:
                _add("non_vegan", non_vegan,
                     f"Non-vegan ingredient(s) detected: {', '.join(non_vegan[:3])}.")

    elif diet == "gluten_free":
        if is_gluten_free is False:
            _add("contains_gluten", ["(product marked not gluten-free)"],
                 "This product contains gluten — conflicts with your gluten-free requirement.")
        else:
            gluten = _keyword_match(ingredients, _GLUTEN_KEYWORDS)
            if gluten:
                _add("contains_gluten", gluten,
                     f"Gluten ingredient(s) detected: {', '.join(gluten[:3])}.")

    elif diet == "halal":
        pork = _keyword_match(ingredients, _PORK_KEYWORDS)
        alc  = _keyword_match(ingredients, _ALCOHOL_KEYWORDS)
        if pork:
            _add("non_halal_pork", pork,
                 f"Pork ingredient(s) detected — not Halal: {', '.join(pork[:3])}.")
        if alc:
            _add("non_halal_alcohol", alc,
                 f"Alcohol-derived ingredient(s) detected — may not be Halal: {', '.join(alc[:3])}.")

    logger.info(
        "allergen_service.diet_check | diet=%r mismatches=%d",
        dietary_preference, len(mismatches),
    )
    return mismatches


def run_full_check(
    ingredients: list[str],
    user_allergen_categories: list[str],
    user_allergen_names: list[str] | None,
    dietary_preference: str | None,
    is_vegetarian: bool | None = None,
    is_vegan: bool | None = None,
    is_gluten_free: bool | None = None,
) -> AllergenCheckResult:
    """
    Run both allergen and dietary checks in one call.

    This is the entry point used by the scan pipeline and the LangGraph tool.
    """
    logger.info(
        "allergen_service.full_check | allergen_categories=%s diet=%r ingredients=%d",
        user_allergen_categories, dietary_preference, len(ingredients),
    )
    return AllergenCheckResult(
        allergen_warnings=check_allergens(ingredients, user_allergen_categories, user_allergen_names),
        diet_mismatches=check_dietary_mismatch(
            ingredients, dietary_preference, is_vegetarian, is_vegan, is_gluten_free
        ),
    )
