"""Tests for ``services.grocery.ingredients``."""

from __future__ import annotations

from app.schemas.status import StatusCode
from services.grocery.ingredients import (
    analyze_ingredients,
    extract_ingredients_block,
)


def test_extract_block_finds_ingredients_section() -> None:
    text = """
    NUTRITION INFORMATION
    Energy 450 kcal

    Ingredients: Refined wheat flour, sugar, edible vegetable oil,
    salt, milk solids, baking powder.

    Storage: store in a cool place.
    """
    block = extract_ingredients_block(text)
    assert block is not None
    assert "wheat flour" in block.lower()
    assert "storage" not in block.lower()


def test_extract_block_returns_none_when_no_header() -> None:
    text = "Just some marketing copy with no ingredients section."
    assert extract_ingredients_block(text) is None


def test_analyze_flags_hidden_sugars() -> None:
    """At least 2 distinct sugar names ⇒ HIDDEN_SUGARS_FOUND."""
    block = (
        "Wheat flour, sugar, glucose syrup, dextrose, maltodextrin, "
        "salt, milk powder."
    )
    findings, count = analyze_ingredients(block)
    codes = [f.code for f in findings]

    assert StatusCode.HIDDEN_SUGARS_FOUND in codes
    assert count == 7


def test_analyze_flags_concerning_e_codes() -> None:
    block = (
        "Refined wheat flour, sugar, palm oil, "
        "colour (E102), preservative (E211), emulsifier (E471)."
    )
    findings, _ = analyze_ingredients(block)
    codes = [f.code for f in findings]

    assert StatusCode.CONCERNING_E_CODES in codes
    e_finding = next(f for f in findings if f.code == StatusCode.CONCERNING_E_CODES)
    assert "E102" in (e_finding.evidence or "")


def test_analyze_ignores_safe_e_codes() -> None:
    """E300 (vitamin C) is safe — should NOT trigger the flag."""
    block = "Sugar, water, antioxidant (E300)."
    findings, _ = analyze_ingredients(block)
    codes = [f.code for f in findings]
    assert StatusCode.CONCERNING_E_CODES not in codes


def test_analyze_flags_long_ingredient_list() -> None:
    items = [f"item{i}" for i in range(15)]
    block = ", ".join(items) + "."
    findings, count = analyze_ingredients(block)
    codes = [f.code for f in findings]
    assert StatusCode.MANY_INGREDIENTS in codes
    assert count == 15


def test_analyze_picks_up_contains_allergen_line() -> None:
    block = "Wheat flour, sugar, milk solids. Contains: Wheat, Soy, Milk."
    findings, _ = analyze_ingredients(block)
    codes = [f.code for f in findings]

    assert StatusCode.ALLERGEN_DECLARATION_FOUND in codes
    found = next(f for f in findings if f.code == StatusCode.ALLERGEN_DECLARATION_FOUND)
    assert "wheat" in (found.evidence or "").lower()


def test_analyze_flags_missing_contains_when_allergen_in_list() -> None:
    """No 'Contains:' line but allergens present in the body ⇒ MISSING."""
    block = "Refined wheat flour, sugar, salt."
    findings, _ = analyze_ingredients(block)
    codes = [f.code for f in findings]
    assert StatusCode.ALLERGEN_DECLARATION_MISSING in codes


def test_analyze_skips_missing_contains_when_no_allergens_present() -> None:
    """Pure water + sugar product shouldn't get a missing-allergen flag."""
    block = "Water, sugar, citric acid."
    findings, _ = analyze_ingredients(block)
    codes = [f.code for f in findings]
    assert StatusCode.ALLERGEN_DECLARATION_MISSING not in codes


def test_analyze_returns_empty_for_no_block() -> None:
    findings, count = analyze_ingredients(None)
    assert findings == []
    assert count is None


def test_extract_block_stops_at_inline_post_ingredients_keywords() -> None:
    """When the OCR collapses the label onto a single line, the block
    extractor must still terminate at obvious post-ingredients sections
    (manufacturer addresses, "PROPRIETARY FOOD", "CONTAINS ADDED…")
    rather than swallowing the rest of the pack."""
    text = (
        "INGREDIENTS: Potato, Edible Vegetable Oil, Sugar, Milk Solids, "
        "Cheese Powder, Spices, Starch. CONTAINS ADDED FLAVOUR. "
        "PROPRIETARY FOOD. Mfd. By: PEPSICO INDIA HOLDINGS PVT. LTD. "
        "Lic. No. 10012022000339"
    )
    block = extract_ingredients_block(text)
    assert block is not None
    assert "Potato" in block
    # The address / regulatory block must NOT bleed into the captured list.
    assert "PEPSICO" not in block.upper()
    assert "PROPRIETARY" not in block.upper()
    assert "CONTAINS ADDED" not in block.upper()


def test_split_filters_out_company_names_and_long_sentences() -> None:
    """Even if the extractor over-captures, the item filter should drop
    obvious non-ingredients before they inflate the count or trigger
    spurious 'many ingredients' warnings."""
    text = (
        "INGREDIENTS: Wheat, Sugar, Salt, "
        "PEPSICO INDIA HOLDINGS PVT. LTD., "
        "Mfd. by: Some Company, "
        "For manufacturing unit address see panel below, "
        "PIN: 148026"
    )
    _, count = analyze_ingredients(extract_ingredients_block(text) or "")
    # Wheat + Sugar + Salt = 3 actual items; the rest must be filtered out.
    assert count == 3


def test_extract_block_caps_at_max_chars() -> None:
    """Pathological labels (no recognisable post-ingredients keyword)
    shouldn't return an unbounded block — cap kicks in."""
    text = "Ingredients: " + ", ".join(f"item{i}" for i in range(200))
    block = extract_ingredients_block(text)
    assert block is not None
    assert len(block) <= 500  # generous upper bound
