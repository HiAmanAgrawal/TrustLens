"""Nutrition table parsing + threshold evaluation.

Indian / Asian packaged-food labels usually print a small two- or
three-column nutrition table:

  Energy           450 kcal       2200 kJ
  Total Fat        18 g
    Saturated Fat   7 g
    Trans Fat       0 g
  Carbohydrates    52 g
    Sugars         28 g
  Sodium          850 mg

Sometimes only one column is given ("per serving"), sometimes two
("per serving | per 100 g"). The OCR pass collapses tabs into newlines or
spaces, so we work line-by-line and extract the numeric part with a
permissive regex rather than trying to align columns visually.

When *both* per-serving and per-100g values are present we always prefer
per-100g — that's what the FSAI traffic-light thresholds are calibrated
on. When only per-serving is available we still parse it but emit
:data:`StatusCode.PER_SERVING_ONLY` so the user knows the comparison is
uncertain.
"""

from __future__ import annotations

import re
from typing import Final

from app.schemas.grocery import Finding
from app.schemas.status import MESSAGES, StatusCode, _DEFAULT_SEVERITY

from ._data import NUTRITION_THRESHOLDS

# Shared unit token. ``per cent`` / ``percent`` / ``%`` are accepted because
# Indian-style labels often state values as a percentage by weight rather
# than in grams ("Saturated Fat content not more than 16.1 per cent by
# weight"). For solid foods, % by weight ≡ g per 100 g, so the
# normalisation is a no-op.
_UNIT_TOKEN: Final[str] = r"g|mg|kcal|cal|kj|%|per\s*cent|percent"

# "[noise] N [unit]" — letting OCR-noise like "content not more than"
# float between the nutrient label and its number lets us still find
# values even when the row has been mangled into a sentence.
_VALUE_TAIL: Final[str] = (
    r"(?:\s+content)?(?:[^0-9\-]|not\s+more\s+than)*?"
    r"(?P<val>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>" + _UNIT_TOKEN + r")?"
)

# Per-nutrient match. Each entry is (canonical_key, regex_with_named_value
# group). The regex captures a number and an optional unit; the
# :func:`_to_g_per_100g` helper normalises the unit on the way out.
#
# Sodium aliases salt because some labels print "Salt 1.2 g" (UK style)
# instead of sodium in mg. We convert salt grams to sodium milligrams
# (× 393.3) so a single threshold can be applied to either form.
_NUTRIENT_ROWS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("trans_fat", re.compile(
        r"\btrans\s*fat(?:ty\s*acid)?s?\b" + _VALUE_TAIL,
        re.IGNORECASE,
    )),
    ("sat_fat", re.compile(
        r"\b(?:saturated|sat\.?)\s*fat\b" + _VALUE_TAIL,
        re.IGNORECASE,
    )),
    # "Total Fat 18 g" — require the explicit ``total`` prefix so the
    # bare ``\bfat\b`` doesn't also match inside "Trans Fat" /
    # "Saturated Fat" (which would mis-credit those values to total fat).
    ("total_fat", re.compile(
        r"\btotal\s+fat\b" + _VALUE_TAIL,
        re.IGNORECASE,
    )),
    # "Sugars 28 g" or "Total Sugars 28 g". Excludes "Added Sugars" line —
    # captured separately so we always report total sugars.
    ("sugar", re.compile(
        r"\b(?:total\s+)?sugars?\b" + _VALUE_TAIL,
        re.IGNORECASE,
    )),
    ("carbohydrate", re.compile(
        r"\b(?:total\s+)?carbohydrate?s?\b" + _VALUE_TAIL,
        re.IGNORECASE,
    )),
    ("protein", re.compile(
        r"\bproteins?\b" + _VALUE_TAIL,
        re.IGNORECASE,
    )),
    ("energy", re.compile(
        r"\benergy\b" + _VALUE_TAIL,
        re.IGNORECASE,
    )),
    ("sodium", re.compile(
        r"\bsodium\b" + _VALUE_TAIL,
        re.IGNORECASE,
    )),
    ("salt", re.compile(
        r"\bsalt\b" + _VALUE_TAIL,
        re.IGNORECASE,
    )),
)

# Heuristic to spot the nutrition section start. We don't enforce it
# (some labels skip the heading entirely and just dump rows) but we use
# it to figure out whether the table itself is present at all. The
# ``[a-z]*`` tail forgives common OCR drift on the long word
# (``NUTRITIONAL`` → ``JWIRIIONAL``-style transcription errors are
# matched by also looking for ``per 100`` / ``approx`` hints below).
_TABLE_HEADER_RE: Final[re.Pattern[str]] = re.compile(
    r"\bnutrition(?:al)?(?:\s+(?:information|facts))?\b",
    re.IGNORECASE,
)

# Secondary header hints that catch labels where the actual word
# "nutrition" was OCR-mangled. Any of these in combination with at least
# one parsed nutrient is enough to call the table present.
_TABLE_HINT_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:per\s*100\s*(?:g|ml)|approx\.?\s*(?:per|values?)|"
    r"per\s*cent\s*by\s*weight|percent\s*by\s*weight)\b",
    re.IGNORECASE,
)

# Detects a "per 100 g" or "per 100ml" basis somewhere in the table.
_PER_100_RE: Final[re.Pattern[str]] = re.compile(
    r"\bper\s*100\s*(?:g|ml)\b",
    re.IGNORECASE,
)
_PER_SERVING_RE: Final[re.Pattern[str]] = re.compile(
    r"\bper\s*serving\b|\bper\s*serv\b",
    re.IGNORECASE,
)
# When a label states values as "X per cent by weight" the basis is
# implicitly per-100 g (a percentage by weight = g per 100 g for solids).
_PERCENT_BY_WEIGHT_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:per\s*cent|percent|%)\s*by\s*weight\b",
    re.IGNORECASE,
)


def parse_nutrition(text: str) -> dict | None:
    """Extract a normalised nutrition dict, or ``None`` if no table found.

    Returns:
        ``None`` if there's no nutrition section we can parse at all.

        ``{"basis": ..., "values": {...}, "table_detected": bool}`` otherwise.
        ``table_detected=True`` with an empty ``values`` dict signals that
        a header / hint was found but no rows could be read — the analyser
        surfaces this as :data:`StatusCode.NUTRITION_TABLE_PARTIAL`.

        Possible value keys (any subset)::

            sodium_mg, trans_fat_g, sat_fat_g, total_fat_g,
            sugar_g, carbohydrate_g, protein_g, energy_kcal
    """
    if not text:
        return None

    has_header = bool(_TABLE_HEADER_RE.search(text))
    has_hint = bool(_TABLE_HINT_RE.search(text))
    has_any_row = any(rx.search(text) for _, rx in _NUTRIENT_ROWS)
    if not (has_header or has_hint or has_any_row):
        return None

    # Try to scope the search to the actual table region — that way a
    # mention of "sugar" elsewhere on the pack ("contains: sugar, salt")
    # doesn't pollute the parsed values.
    region = _scope_to_table(text)

    if _PER_100_RE.search(region) or _PERCENT_BY_WEIGHT_RE.search(region):
        basis = "per_100g"
    elif _PER_SERVING_RE.search(region):
        basis = "per_serving"
    else:
        basis = "unknown"

    values: dict[str, float] = {}
    for key, rx in _NUTRIENT_ROWS:
        m = rx.search(region)
        if not m:
            continue
        try:
            raw_val = float(m.group("val").replace(",", "."))
        except (TypeError, ValueError):
            continue
        unit = _normalise_unit(m.group("unit"))

        if key == "sodium":
            values["sodium_mg"] = _to_mg(raw_val, unit)
        elif key == "salt":
            # Convert salt → sodium so we have one canonical value to
            # compare against the threshold. 1 g salt ≈ 393.3 mg sodium.
            if unit == "mg":
                sodium_mg = _to_mg(raw_val, unit) * 0.3933
            else:
                sodium_mg = raw_val * 393.3
            # Per-serving salt is often the only sodium-equivalent value
            # available; only override sodium_mg if we don't already have one.
            values.setdefault("sodium_mg", sodium_mg)
        elif key == "trans_fat":
            values["trans_fat_g"] = _to_g(raw_val, unit)
        elif key == "sat_fat":
            values["sat_fat_g"] = _to_g(raw_val, unit)
        elif key == "total_fat":
            values["total_fat_g"] = _to_g(raw_val, unit)
        elif key == "sugar":
            values["sugar_g"] = _to_g(raw_val, unit)
        elif key == "carbohydrate":
            values["carbohydrate_g"] = _to_g(raw_val, unit)
        elif key == "protein":
            values["protein_g"] = _to_g(raw_val, unit)
        elif key == "energy":
            values["energy_kcal"] = raw_val

    if values:
        return {"basis": basis, "values": values, "table_detected": True}

    # Header / hint matched but no rows parsed — useful signal for the
    # caller (we know the table exists, we just couldn't read it).
    if has_header or has_hint:
        return {"basis": basis, "values": {}, "table_detected": True}

    return None


def evaluate_nutrition(parsed: dict | None) -> list[Finding]:
    """Apply the FSAI thresholds and a basis-of-comparison check.

    Also fires :data:`StatusCode.NUTRITION_TABLE_PARTIAL` when a table
    was detected but no rows could be parsed — that's a meaningfully
    different signal from "no table at all" and helps the user
    understand why we couldn't grade the nutrition.
    """
    if not parsed:
        return []

    findings: list[Finding] = []
    values = parsed.get("values", {})
    basis = parsed.get("basis", "unknown")

    if parsed.get("table_detected") and not values:
        findings.append(_finding(StatusCode.NUTRITION_TABLE_PARTIAL))
        return findings

    if basis == "per_serving":
        findings.append(_finding(StatusCode.PER_SERVING_ONLY))

    # Threshold checks. We *only* fire these when the basis is per_100g —
    # otherwise the comparison is meaningless. The per_serving warning
    # above tells the user we couldn't apply them.
    if basis != "per_100g":
        return findings

    if (sodium := values.get("sodium_mg")) is not None and sodium > NUTRITION_THRESHOLDS["sodium_per_100g_mg"]:
        findings.append(_finding(StatusCode.HIGH_SODIUM, evidence=f"{sodium:g} mg / 100 g"))
    if (trans := values.get("trans_fat_g")) is not None and trans > NUTRITION_THRESHOLDS["trans_fat_per_100g_g"]:
        findings.append(_finding(StatusCode.TRANS_FAT_PRESENT, evidence=f"{trans:g} g / 100 g"))
    if (sugar := values.get("sugar_g")) is not None and sugar > NUTRITION_THRESHOLDS["sugar_per_100g_g"]:
        findings.append(_finding(StatusCode.HIGH_SUGAR, evidence=f"{sugar:g} g / 100 g"))
    if (sat := values.get("sat_fat_g")) is not None and sat > NUTRITION_THRESHOLDS["sat_fat_per_100g_g"]:
        findings.append(_finding(StatusCode.HIGH_SAT_FAT, evidence=f"{sat:g} g / 100 g"))
    if (total := values.get("total_fat_g")) is not None and total > NUTRITION_THRESHOLDS["total_fat_per_100g_g"]:
        findings.append(_finding(StatusCode.HIGH_TOTAL_FAT, evidence=f"{total:g} g / 100 g"))

    return findings


def _scope_to_table(text: str) -> str:
    """Trim ``text`` to the region around the nutrition table.

    Keeps about 1.5 KB after the heading. Returns the full text if no
    heading is present (some Indian labels list nutrient rows without
    any "Nutrition Information" title).
    """
    m = _TABLE_HEADER_RE.search(text)
    if not m:
        return text
    end = min(len(text), m.end() + 1500)
    return text[m.start() : end]


def _normalise_unit(raw: str | None) -> str:
    """Squash spacing / casing variants of the unit token."""
    if not raw:
        return ""
    cleaned = raw.lower().replace(" ", "")
    if cleaned in {"percent", "percent.", "percent,"}:
        return "%"
    return cleaned


def _to_mg(val: float, unit: str) -> float:
    """Normalise a (value, unit) pair to milligrams."""
    if unit == "g":
        return val * 1000.0
    if unit == "%":
        # 1 g / 100 g = 1 % by weight = 1000 mg / 100 g.
        return val * 1000.0
    return val


def _to_g(val: float, unit: str) -> float:
    """Normalise a (value, unit) pair to grams (per 100 g basis)."""
    if unit == "mg":
        return val / 1000.0
    if unit == "%":
        # % by weight ≡ g per 100 g for solids — already in target units.
        return val
    return val


def _finding(code: StatusCode, *, evidence: str | None = None) -> Finding:
    return Finding(
        code=code,
        severity=_DEFAULT_SEVERITY.get(code, "info"),
        message=MESSAGES[code],
        evidence=evidence or None,
    )
