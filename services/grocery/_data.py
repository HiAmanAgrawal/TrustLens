"""Shared constants for the grocery analyser.

Kept in one tiny module so the lists are easy to audit and extend without
touching analysis logic. None of these are hot-path; the cost is in the
regex compilation that consumers do on top of them.

Sources:
- HIDDEN_SUGAR_NAMES: FSSAI consumer guidance + WHO sugar nomenclature.
- CONCERNING_E_CODES: EU/UK Food Standards Agency advisories on additives
  with documented hyperactivity, allergy, or carcinogenicity links. Many
  E-numbers are perfectly safe (e.g. E300 = vitamin C); only flag the ones
  consumers commonly want to know about.
- NUTRITION_THRESHOLDS: UK FSA / FSAI traffic-light high thresholds, the
  most widely-cited consumer-facing benchmarks for "high in X".
"""

from __future__ import annotations

from typing import Final


HIDDEN_SUGAR_NAMES: Final[tuple[str, ...]] = (
    "sucrose",
    "fructose",
    "glucose",
    "dextrose",
    "maltose",
    "lactose",
    "galactose",
    "corn syrup",
    "high fructose corn syrup",
    "invert sugar",
    "cane sugar",
    "cane juice",
    "fruit concentrate",
    "fruit juice concentrate",
    "molasses",
    "honey",
    "agave nectar",
    "rice syrup",
    "malt syrup",
    "maltodextrin",
    "barley malt",
    "treacle",
    "syrup",
)

CONCERNING_E_CODES: Final[frozenset[str]] = frozenset(
    {
        # ---- Synthetic colours linked to hyperactivity (EU "Southampton six")
        "E102",  # Tartrazine
        "E104",  # Quinoline yellow
        "E110",  # Sunset yellow
        "E122",  # Carmoisine
        "E124",  # Ponceau 4R
        "E129",  # Allura red
        "E127",  # Erythrosine — historically banned in some jurisdictions
        # ---- Preservatives with allergy / asthma signals
        "E211",  # Sodium benzoate
        "E220",  # Sulphur dioxide
        "E221",  # Sodium sulphite
        "E223",  # Sodium metabisulphite
        "E249",  # Potassium nitrite
        "E250",  # Sodium nitrite
        "E251",  # Sodium nitrate
        "E252",  # Potassium nitrate
        # ---- Antioxidants with toxicology debate
        "E320",  # BHA
        "E321",  # BHT
        # ---- Emulsifiers/thickeners with gut-microbiome studies
        "E466",  # Carboxymethyl cellulose
        "E471",  # Mono- and diglycerides
        # ---- Flavour enhancers (the classic "MSG family")
        "E621",  # Monosodium glutamate
        "E631",  # Disodium inosinate
        "E635",  # Disodium 5'-ribonucleotides
    }
)

VAGUE_CLAIMS: Final[tuple[tuple[str, str], ...]] = (
    # (label_for_finding, regex_pattern). Keep patterns tight so we don't
    # match the same word inside a regulated phrase
    # (e.g. "natural flavouring permitted" should still flag — that's fine —
    # but "naturally occurring" should not double-fire).
    ("natural", r"\bnatural(?:ly)?\b"),
    ("farm_fresh", r"\bfarm[\s\-]?fresh\b"),
    ("no_preservatives", r"\bno\s+(?:added\s+)?preservatives?\b"),
    ("low_fat", r"\blow[\s\-]?fat\b"),
    ("multigrain", r"\bmulti[\s\-]?grain\b"),
    ("homestyle", r"\bhome[\s\-]?style\b"),
    ("doctor_recommended", r"\bdoctor[\s\-]?recommended\b"),
)

ALLERGENS: Final[tuple[str, ...]] = (
    "wheat",
    "gluten",
    "soy",
    "soya",
    "milk",
    "dairy",
    "egg",
    "peanut",
    "peanuts",
    "tree nut",
    "tree nuts",
    "almond",
    "cashew",
    "walnut",
    "hazelnut",
    "fish",
    "shellfish",
    "sesame",
    "mustard",
    "celery",
    "sulphite",
    "sulphites",
)


# Per-100g thresholds (UK FSA / FSAI "high" band). Values above these get
# flagged as a warning. Trans fat is a hard-zero target — the WHO calls
# for its elimination from the food supply, so any non-zero amount fires.
NUTRITION_THRESHOLDS: Final[dict[str, float]] = {
    "sodium_per_100g_mg": 600.0,
    "trans_fat_per_100g_g": 0.0,
    "sugar_per_100g_g": 22.5,
    "sat_fat_per_100g_g": 5.0,
    "total_fat_per_100g_g": 17.5,
}


# Threshold for "this ingredients list is long". Heavily-processed foods
# tend to have well over 10 distinct items.
MANY_INGREDIENTS_THRESHOLD: Final[int] = 10


# Threshold for "we found multiple sugars hiding under different names" —
# any single sweetener slipping in is normal; a stack of 2+ in the same
# list is the deceptive pattern the consumer guide warns about.
HIDDEN_SUGARS_THRESHOLD: Final[int] = 2
