"""
Input parsers for onboarding responses.

WHY rule-based instead of LLM-based:
  Onboarding answers are structured (diet = one of 6 values, allergies = a list,
  medicines = a list). Rule-based parsing is:
    1. Deterministic — no hallucination risk.
    2. Zero-latency — no extra API call during onboarding.
    3. Auditable — the match logic is readable and testable.

  We only fall back to an LLM when the user types something genuinely ambiguous
  that the rules can't handle (future work, not Phase 2).

ALLERGEN AUTO-CLASSIFICATION:
  The allergen parser tries to classify free-text allergens into
  AllergenCategoryEnum values for structured DB storage. This enables the
  "find all products containing X" query without array operators.
"""

from __future__ import annotations

import re

from app.models.enums import AllergenCategoryEnum, DietaryPreferenceEnum


# ---------------------------------------------------------------------------
# Diet parser
# ---------------------------------------------------------------------------

# Maps keyword → DietaryPreferenceEnum value.
# Ordered most-specific first (vegan before vegetarian).
_DIET_KEYWORD_MAP: list[tuple[list[str], DietaryPreferenceEnum]] = [
    # Most-specific first to prevent partial matches (e.g. "non-veg" must beat "veg")
    (["non veg", "non-veg", "nonveg", "meat",
      "chicken", "fish", "egg", "मांसाहारी",
      "non vegetarian", "non-vegetarian"],        DietaryPreferenceEnum.NON_VEGETARIAN),
    (["vegan", "pure veg"],                       DietaryPreferenceEnum.VEGAN),
    (["jain"],                                    DietaryPreferenceEnum.JAIN),
    (["halal"],                                   DietaryPreferenceEnum.HALAL),
    (["kosher"],                                  DietaryPreferenceEnum.KOSHER),
    (["gluten free", "gluten-free", "gf"],        DietaryPreferenceEnum.GLUTEN_FREE),
    (["vegetarian", "veg", "veggie", "शाकाहारी"],  DietaryPreferenceEnum.VEGETARIAN),
]


def parse_diet(text: str) -> DietaryPreferenceEnum | None:
    """
    Return the DietaryPreferenceEnum that matches ``text``, or None if no match.

    Normalises the input to lowercase with collapsed whitespace before matching.
    """
    normalised = re.sub(r"\s+", " ", text.strip().lower())
    for keywords, preference in _DIET_KEYWORD_MAP:
        if any(kw in normalised for kw in keywords):
            return preference
    return None


# ---------------------------------------------------------------------------
# Allergen parser
# ---------------------------------------------------------------------------

# Maps AllergenCategoryEnum → representative keywords found in user text.
_ALLERGEN_KEYWORD_MAP: dict[AllergenCategoryEnum, list[str]] = {
    AllergenCategoryEnum.PEANUTS:     ["peanut", "groundnut", "moongfali"],
    AllergenCategoryEnum.MILK:        ["milk", "dairy", "lactose", "doodh"],
    AllergenCategoryEnum.EGGS:        ["egg", "anda"],
    AllergenCategoryEnum.GLUTEN:      ["gluten", "wheat", "atta", "maida"],
    AllergenCategoryEnum.TREE_NUTS:   ["almond", "cashew", "walnut", "pistachio",
                                        "hazelnut", "pecan", "kaju", "badam"],
    AllergenCategoryEnum.FISH:        ["fish", "mackerel", "tuna", "salmon", "machli"],
    AllergenCategoryEnum.CRUSTACEANS: ["shrimp", "prawn", "crab", "lobster", "jhinga"],
    AllergenCategoryEnum.SOYBEANS:    ["soy", "tofu", "soya"],
    AllergenCategoryEnum.SESAME:      ["sesame", "til", "tahini"],
    AllergenCategoryEnum.MUSTARD:     ["mustard", "sarson"],
    AllergenCategoryEnum.SULPHITES:   ["sulphite", "sulfite", "so2", "wine"],
    AllergenCategoryEnum.COCONUT:     ["coconut", "nariyal"],
    AllergenCategoryEnum.CORN:        ["corn", "maize", "makka"],
}

# Patterns that mean "I have no allergies"
_NO_ALLERGY_PATTERNS = re.compile(
    r"\b(none|no|nope|nil|nothing|n\/a|skip|na)\b", re.IGNORECASE
)


def parse_allergies(text: str) -> tuple[list[str], list[AllergenCategoryEnum]]:
    """
    Parse a free-text allergy list.

    Returns:
      raw_names   — list of allergen strings as the user typed them
      categories  — classified AllergenCategoryEnum values (may be shorter than raw_names)

    Example:
      "I'm allergic to peanuts and milk" →
        raw_names=["peanuts", "milk"], categories=[PEANUTS, MILK]

      "tree nuts, gluten" →
        raw_names=["tree nuts", "gluten"], categories=[TREE_NUTS, GLUTEN]
    """
    if _NO_ALLERGY_PATTERNS.search(text):
        return [], []

    # Split on commas, "and", "&", or semicolons
    parts = re.split(r"[,;&]|\band\b", text.lower())
    raw_names: list[str] = []
    categories: list[AllergenCategoryEnum] = []

    for part in parts:
        clean = part.strip()
        # Remove filler phrases
        clean = re.sub(
            r"\b(i('m| am)? (allergic to|intolerant to|avoid)|i have a[n]? allergy to)\b",
            "", clean,
        ).strip()
        if not clean:
            continue

        raw_names.append(clean)

        # Try to classify
        for cat, keywords in _ALLERGEN_KEYWORD_MAP.items():
            if any(kw in clean for kw in keywords):
                if cat not in categories:
                    categories.append(cat)
                break

    return raw_names, categories


# ---------------------------------------------------------------------------
# Medicine name parser
# ---------------------------------------------------------------------------

_NO_MEDICINE_PATTERNS = re.compile(
    r"\b(none|no|nope|nil|nothing|n\/a|skip|na)\b", re.IGNORECASE
)
# Tablet strength pattern to strip (e.g. "500mg", "10 mg", "1g")
_STRENGTH_PATTERN = re.compile(r"\b\d+\s*(mg|mcg|g|ml|iu)\b", re.IGNORECASE)


def parse_medicines(text: str) -> list[str]:
    """
    Parse a free-text list of medicine names.

    Returns a cleaned list of medicine name strings, ready for DB storage.
    Strength suffixes ("500mg") are stripped since the user is giving us the
    brand/generic name, not a prescription dose.

    Example:
      "Metformin 500mg, Aspirin and Amlodipine" → ["Metformin", "Aspirin", "Amlodipine"]
    """
    if _NO_MEDICINE_PATTERNS.search(text):
        return []

    parts = re.split(r"[,;&]|\band\b", text, flags=re.IGNORECASE)
    medicines: list[str] = []

    for part in parts:
        clean = _STRENGTH_PATTERN.sub("", part).strip()
        # Title-case so "metformin" → "Metformin"
        clean = " ".join(w.capitalize() for w in clean.split())
        if clean and len(clean) >= 2:
            medicines.append(clean)

    return medicines


# ---------------------------------------------------------------------------
# Name parser (minimal — just clean whitespace/punctuation)
# ---------------------------------------------------------------------------

def parse_name(text: str) -> str:
    """
    Extract a clean name from user input.

    Handles:
      "My name is Rahul" → "Rahul"
      "I'm Priya Sharma" → "Priya Sharma"
      "rahul" → "Rahul"
    """
    # Remove common preamble phrases
    cleaned = re.sub(
        r"(?i)^(my name is|i am|i'm|call me|name['s]* )",
        "",
        text.strip(),
    ).strip()
    # Remove trailing punctuation
    cleaned = cleaned.rstrip(".,!?")
    # Title-case
    return " ".join(w.capitalize() for w in cleaned.split()) if cleaned else text.strip()
