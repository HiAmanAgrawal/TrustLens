"""Matcher engine — compares OCR'd label text to scraped manufacturer-page text.

Rule-based and deterministic on purpose. We extract candidate fields (batch
number, MFG/EXP dates, manufacturer line, drug name) from each side with
small regexes, then fuzzy-compare the overlapping fields with rapidfuzz.

No LLM calls here — that lives in the OCR fallback. Keeping the matcher pure
makes it trivial to unit-test and predictable to debug.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from rapidfuzz import fuzz

VerdictLabel = Literal["high_risk", "caution", "safe", "unverifiable"]


@dataclass(frozen=True)
class Verdict:
    score: int                                          # 0–10
    verdict: VerdictLabel
    summary: str                                        # plain-language, ready for the user
    evidence: list[str] = field(default_factory=list)   # per-field comparison strings
    barcode_payload: str | None = None
    label_text: str | None = None                       # raw OCR output, surfaced for debugging
    page_text: str | None = None                        # raw scraped text, ditto
    label_fields: dict[str, str] = field(default_factory=dict)
    page_fields: dict[str, str] = field(default_factory=dict)


# --- Field extraction --------------------------------------------------------
#
# Pharma packs in India use a small handful of common label conventions, but
# manufacturer verification portals use a *different* set of conventions
# again (full English phrases like "Date of expiry", "Brand Name:", "Name and
# Address of the manufacturer"). The regexes below have to handle both.
#
# Rule of thumb: keywords are a permissive alternation, optional separators
# are followed by an optional newline (portals often put the value on the
# next line after the colon), and date captures allow ``.`` and a single
# space (real labels say things like ``MAR.2025`` and ``MAY 25``).

_BATCH_RE = re.compile(
    # Matches: "Batch: ABC123", "Batch No.: ABC123", "B. No: ABC123",
    # "Batch number:\nDOBS3975", "Lot ABC123".
    # ``b\.`` requires the literal dot so we don't false-match the "B" in
    # words like "Brand" or "Bottle". ``batch`` and ``lot`` use word
    # boundaries which already give them a clean exit.
    r"(?:\bbatch\b|\blot\b|\bb\.)\s*(?:no\.?|number)?\s*[:\-]?\s*\n?\s*([A-Z0-9\-]{3,})",
    re.I,
)
# Date capture: letters, digits, '.', '/', '-', and at most one internal
# space — enough for "MAR.2025", "MAY 25", "01/2024", "12-2026". We
# explicitly stop before another all-caps keyword (EXP / MFG / DT) so a
# label like "MFG: MAY 25 EXP: ..." doesn't bleed into the next field.
_DATE_VALUE = (
    # First token (e.g. "MAR.2025" or "MAY"), optionally followed by ONE
    # space and a second token (e.g. "MAY 25"). Crucially a *literal* space,
    # not generic whitespace — \s would let us swallow a newline + the next
    # field's keyword.
    r"([0-9A-Z][0-9A-Z./\-]{1,8}(?: [0-9A-Z][0-9A-Z./\-]{0,8})?)"
    r"(?=\s|$|[.,;])"
)
_MFG_DATE_RE = re.compile(
    # "Mfg Date:", "Mfd:", "Manufactured on:", "Manufacturing Date:",
    # "Date of manufacturing:", "MFG. DT.".
    r"(?:mfg|mfd|manufactur(?:ed|ing)|date\s+of\s+manufactur(?:ing|e))"
    r"\s*\.?\s*(?:date|dt|on)?\s*\.?\s*[:\-]?\s*\n?\s*" + _DATE_VALUE,
    re.I,
)
_EXP_DATE_RE = re.compile(
    # "Exp:", "Expiry:", "Use before:", "Date of expiry:", "EXP. DT.".
    r"(?:exp(?:iry|\.?)?|use\s*before|date\s+of\s+expir(?:y|e))"
    r"\s*(?:date|dt)?\s*\.?\s*[:\-]?\s*\n?\s*" + _DATE_VALUE,
    re.I,
)
_MFG_NAME_RE = re.compile(
    # Two shapes:
    #   1. "Manufactured/Marketed/Mktd by [: ] NAME" (label-style)
    #   2. "Manufacturer:\nNAME" (portal-style — colon then newline then name)
    # Captures up to 80 chars of the name; trailing punctuation gets trimmed.
    r"(?:"
    r"(?:manufactured|mfd|mktd|marketed)\s*by\s*:?"
    r"|"
    r"(?:name\s+(?:and\s+address\s+)?of\s+the\s+manufacturer|manufacturer)\s*[:\-]"
    r")\s*\n?\s*([A-Z][A-Za-z0-9 .,&'\-]{4,80})",
    re.I,
)
# Brand name lines on portals: "Brand Name: DOLO-650".
_BRAND_RE = re.compile(
    r"\bbrand\s*name\s*[:\-]?\s*\n?\s*([A-Z][A-Z0-9\-]{2,40})",
    re.I,
)
# Generic / proper drug name: "Proper and Generic name of the drug:\nParacetamol Tablets IP".
_GENERIC_NAME_RE = re.compile(
    r"(?:proper\s+(?:and\s+generic\s+)?name\s+of\s+the\s+drug|generic\s+name)"
    r"\s*[:\-]?\s*\n?\s*([A-Z][A-Za-z0-9 .,'\-]{3,60})",
    re.I,
)


def _extract_fields(text: str | None) -> dict[str, str]:
    """Pull a small, well-known set of fields out of free-form text.

    Returns a dict with whichever of {batch, mfg_date, exp_date, manufacturer,
    drug_name, brand_name} we could find. Missing keys mean "not present",
    not "empty".
    """
    if not text:
        return {}

    fields: dict[str, str] = {}
    if m := _BATCH_RE.search(text):
        fields["batch"] = m.group(1).strip().upper()
    if m := _MFG_DATE_RE.search(text):
        fields["mfg_date"] = _normalise_date(m.group(1))
    if m := _EXP_DATE_RE.search(text):
        fields["exp_date"] = _normalise_date(m.group(1))
    if m := _MFG_NAME_RE.search(text):
        # Trim trailing junk (commas, "Pvt. Ltd." etc. are kept; surrounding
        # whitespace and stray dots are not).
        fields["manufacturer"] = m.group(1).strip(" .,").strip()
    if m := _BRAND_RE.search(text):
        fields["brand_name"] = m.group(1).strip().upper()

    # Pass already-extracted values so the SKU heuristic doesn't return the
    # batch number (which is also "uppercase + digits") as the drug name.
    drug = _pick_drug_name(text, fields.get("brand_name"), exclude={fields.get("batch")})
    if drug:
        fields["drug_name"] = drug

    return fields


def _normalise_date(raw: str) -> str:
    """Tidy a captured date: strip trailing whitespace/punctuation, upper-case."""
    return raw.strip(" .,-").upper()


def _pick_drug_name(
    text: str, brand_hint: str | None, *, exclude: set[str | None] | None = None
) -> str:
    """Pick a drug name in priority order:

    1. ``Brand Name:`` already extracted → use as-is.
    2. A "name of the drug" / "generic name" line (portal-style).
    3. A SKU-shaped token like ``DOLO-650`` (capitalised + contains a digit
       or dash). These are almost always the brand name on a pack.
    4. The longest capitalised alphabetic token (e.g. ``Cetirizine``),
       skipping obvious non-drug words.

    ``exclude`` lets callers pass in tokens that are *known* to be other
    fields (most importantly, the batch number) so the SKU heuristic doesn't
    accidentally return them.
    """
    if brand_hint:
        return brand_hint
    if m := _GENERIC_NAME_RE.search(text):
        return m.group(1).strip(" .,").strip()

    excluded = {(e or "").upper() for e in (exclude or set())}
    tokens = re.findall(r"\b[A-Z][A-Za-z0-9\-]{2,}\b", text)

    def _ok(tok: str) -> bool:
        return tok.lower() not in _STOPWORDS and tok.upper() not in excluded

    sku_like = [
        t for t in tokens if _ok(t) and (any(c.isdigit() for c in t) or "-" in t)
    ]
    if sku_like:
        return max(sku_like, key=len)

    plain = [t for t in tokens if _ok(t)]
    return max(plain, key=len) if plain else ""


# Words that look like drug names to the naive longest-token heuristic but
# obviously aren't. Keep this list focused on words we've actually seen
# tripping the matcher in the wild — false positives matter less than
# silently dropping a real candidate.
_STOPWORDS = {
    "manufactured",
    "manufacturing",
    "manufacturer",
    "marketed",
    "tablets",
    "capsules",
    "expiry",
    "batch",
    "company",
    "pharmaceuticals",
    "pharma",
    "limited",
    "address",
    "powered",
    "lifesciences",
    "validate",
    "valid",
    "scan",
    "history",
    "location",
    "available",
    "india",
    "registered",
    "trade",
    "mark",
}


# --- Comparison --------------------------------------------------------------


def _compare(label: dict[str, str], page: dict[str, str]) -> tuple[float, list[str]]:
    """Fuzzy-compare overlapping fields. Returns (mean_ratio_0_to_1, evidence).

    ``token_set_ratio`` handles re-ordered tokens, punctuation drift, and
    pluralisation — all common between a printed label and a web page.
    """
    shared = sorted(set(label) & set(page))
    if not shared:
        return 0.0, []

    ratios: list[float] = []
    evidence: list[str] = []
    for key in shared:
        ratio = fuzz.token_set_ratio(label[key], page[key]) / 100.0
        ratios.append(ratio)
        evidence.append(f"{key}: label={label[key]!r} vs page={page[key]!r} ({int(ratio * 100)}%)")

    return sum(ratios) / len(ratios), evidence


def _label_for(score_pct: int, has_both_sides: bool) -> tuple[VerdictLabel, str]:
    """Map a 0–100 score to a verdict label + 1-sentence summary.

    "Unverifiable" is reserved for the case where one whole side is missing
    (no OCR or no scrape) — we never default to "safe" on missing data.
    """
    if not has_both_sides:
        return "unverifiable", (
            "We couldn't compare label and source — one of them was missing or unreadable."
        )
    if score_pct >= 80:
        return "safe", "Label matches the manufacturer's information."
    if score_pct >= 50:
        return "caution", "Label and manufacturer information partially match — please double-check."
    return "high_risk", (
        "Label and manufacturer information disagree significantly. Treat with caution."
    )


async def match(
    *,
    barcode_payload: str | None,
    ocr_text: str | None,
    scrape_data: dict[str, Any] | None = None,
) -> Verdict:
    """Produce a verdict by comparing the two sides we have.

    - ``barcode_payload`` is included in the response so clients can render it.
    - ``ocr_text`` is the label transcription (None on the code-text path).
    - ``scrape_data`` is whatever ``services.scraper`` produced (None when the
      barcode wasn't a URL or the scrape failed).
    """
    page_text: str | None = None
    if scrape_data:
        # The generic scraper packs both title and visible text — concatenate
        # so the field extractor sees one stream.
        page_text = " ".join(
            str(scrape_data.get(k, "")) for k in ("title", "visible_text") if scrape_data.get(k)
        ).strip() or None

    label_fields = _extract_fields(ocr_text)
    page_fields = _extract_fields(page_text)

    has_both_sides = bool(ocr_text) and bool(page_text)
    mean_ratio, evidence = _compare(label_fields, page_fields)
    score_pct = int(round(mean_ratio * 100))
    score_0_10 = max(0, min(10, round(score_pct / 10)))

    verdict_label, summary = _label_for(score_pct, has_both_sides)

    return Verdict(
        score=score_0_10,
        verdict=verdict_label,
        summary=summary,
        evidence=evidence,
        barcode_payload=barcode_payload,
        label_text=ocr_text,
        page_text=page_text,
        label_fields=label_fields,
        page_fields=page_fields,
    )
