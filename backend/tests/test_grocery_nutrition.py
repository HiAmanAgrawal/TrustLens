"""Tests for ``services.grocery.nutrition``."""

from __future__ import annotations

from app.schemas.status import StatusCode
from services.grocery.nutrition import evaluate_nutrition, parse_nutrition


def test_parse_nutrition_returns_none_when_no_table() -> None:
    assert parse_nutrition("Just some marketing copy.") is None


def test_parse_per_100g_table() -> None:
    text = """
    NUTRITION INFORMATION (per 100 g)
    Energy           450 kcal
    Total Fat        18 g
    Saturated Fat    7 g
    Trans Fat        0.5 g
    Carbohydrates    52 g
    Sugars           28 g
    Sodium           750 mg
    """
    parsed = parse_nutrition(text)

    assert parsed is not None
    assert parsed["basis"] == "per_100g"
    values = parsed["values"]
    assert values["sodium_mg"] == 750.0
    assert values["trans_fat_g"] == 0.5
    assert values["sugar_g"] == 28.0
    assert values["sat_fat_g"] == 7.0


def test_evaluate_per_100g_thresholds_fire() -> None:
    parsed = {
        "basis": "per_100g",
        "values": {
            "sodium_mg": 750,
            "trans_fat_g": 0.5,
            "sugar_g": 28,
            "sat_fat_g": 7,
        },
    }
    findings = evaluate_nutrition(parsed)
    codes = [f.code for f in findings]

    assert StatusCode.HIGH_SODIUM in codes
    assert StatusCode.TRANS_FAT_PRESENT in codes
    assert StatusCode.HIGH_SUGAR in codes
    assert StatusCode.HIGH_SAT_FAT in codes
    assert StatusCode.PER_SERVING_ONLY not in codes


def test_evaluate_per_serving_only_warns_and_skips_thresholds() -> None:
    parsed = {
        "basis": "per_serving",
        "values": {"sodium_mg": 9999, "sugar_g": 999},
    }
    findings = evaluate_nutrition(parsed)
    codes = [f.code for f in findings]

    assert StatusCode.PER_SERVING_ONLY in codes
    assert StatusCode.HIGH_SODIUM not in codes
    assert StatusCode.HIGH_SUGAR not in codes


def test_low_values_dont_trigger_thresholds() -> None:
    parsed = {
        "basis": "per_100g",
        "values": {
            "sodium_mg": 100,
            "trans_fat_g": 0,
            "sugar_g": 5,
            "sat_fat_g": 1,
        },
    }
    assert evaluate_nutrition(parsed) == []


def test_parse_handles_salt_to_sodium_conversion() -> None:
    """UK-style 'Salt 1.0 g' → 393 mg sodium ≈ above the 600 mg threshold? No:
    one gram of salt is ~393 mg sodium, below 600. Use 2 g for a clear 'high'."""
    text = """
    Nutrition Information per 100 g
    Salt 2 g
    """
    parsed = parse_nutrition(text)
    assert parsed is not None
    assert parsed["values"].get("sodium_mg", 0) > 600  # threshold for HIGH_SODIUM


def test_parse_returns_partial_table_when_only_header_present() -> None:
    """A header (or "per 100 g" hint) with no readable rows should signal
    a partial table, not a missing one. The caller surfaces the difference
    via :data:`StatusCode.NUTRITION_TABLE_PARTIAL`.
    """
    text = "Nutrition Information goes here later."
    parsed = parse_nutrition(text)

    assert parsed is not None
    assert parsed["values"] == {}
    assert parsed["table_detected"] is True

    findings = evaluate_nutrition(parsed)
    codes = [f.code for f in findings]
    assert StatusCode.NUTRITION_TABLE_PARTIAL in codes


def test_parse_picks_up_total_fat_carbs_protein_energy() -> None:
    """Newer parser should populate every nutrient row in the standard
    Indian-format table, not just sodium/sugar/sat-fat/trans-fat."""
    text = """
    NUTRITION INFORMATION (Per 100 g)
    Energy           544 kcal
    Protein          7.8 g
    Total Carbohydrate 51.6 g
    Sugars           2.0 g
    Total Fat        34.0 g
    """
    parsed = parse_nutrition(text)
    assert parsed is not None
    values = parsed["values"]

    assert values.get("energy_kcal") == 544
    assert values.get("protein_g") == 7.8
    assert values.get("carbohydrate_g") == 51.6
    assert values.get("sugar_g") == 2.0
    assert values.get("total_fat_g") == 34.0


def test_evaluate_fires_high_total_fat_above_17_5() -> None:
    parsed = {
        "basis": "per_100g",
        "values": {"total_fat_g": 34.0},
        "table_detected": True,
    }
    codes = [f.code for f in evaluate_nutrition(parsed)]
    assert StatusCode.HIGH_TOTAL_FAT in codes


def test_parse_handles_percent_by_weight_basis() -> None:
    """Indian labels often state values as 'X per cent by weight' instead
    of grams. For solids, % by weight ≡ g per 100 g, so the parser should
    treat the row as per-100g and apply thresholds accordingly."""
    text = """
    NUTRITION INFORMATION (APPROX.)
    Saturated Fat content not more than 16.1 per cent by weight.
    Trans Fat content not more than 0.5 per cent by weight.
    """
    parsed = parse_nutrition(text)
    assert parsed is not None
    assert parsed["basis"] == "per_100g"
    assert parsed["values"].get("sat_fat_g") == 16.1
    assert parsed["values"].get("trans_fat_g") == 0.5

    codes = [f.code for f in evaluate_nutrition(parsed)]
    assert StatusCode.HIGH_SAT_FAT in codes
    assert StatusCode.TRANS_FAT_PRESENT in codes
