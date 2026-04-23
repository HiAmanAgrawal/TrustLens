"""Matcher engine — compares OCR'd label text to scraped manufacturer-page text.

Rule-based and deterministic on purpose. We extract candidate fields (batch
number, MFG/EXP dates, manufacturer line, drug name) from each side with
small regexes, then fuzzy-compare the overlapping fields with rapidfuzz.

No LLM calls here — that lives in the OCR fallback. Keeping the matcher pure
makes it trivial to unit-test and predictable to debug.
"""

from __future__ import annotations

import re
from collections import Counter
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
# Date capture: must look like an actual date so a stray "Mfg. Lic. No."
# never gets mistaken for a manufacturing date. Three accepted shapes:
#   - month abbreviation + year, optional day prefix:  MAR.2025, MAY 25,
#     15-MAR-2025, APR. 28
#   - numeric month + year:                            01/2024, 12-2026
# Anything that doesn't fit one of those (e.g. "LIC. NO", "M/600/2012")
# falls through and the regex keeps searching for the *real* date later
# in the text.
_MONTH = r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
_DATE_VALUE = (
    r"("
    r"(?:\d{1,2}[./\-\s])?" + _MONTH + r"[.\s/\-]*\d{2,4}"
    r"|"
    r"(?:0?[1-9]|1[0-2])[./\-]\d{2,4}"
    r")"
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
# Manufacturing license number(s). Real labels often show two adjacent
# codes — a primary licence ("M/600/2012") and a sub-code ("ML24F-0043/C")
# on the same line. We capture both so neither can sneak through the
# drug-name picker as a fake brand.
_LIC_NO_RE = re.compile(
    r"(?:mfg\.?\s*lic\.?\s*no\.?|manufacturing\s+licen[sc]e\s+(?:no\.?|number))"
    r"\s*[:\-]?\s*\n?\s*([A-Z0-9/\-]+(?:[ \t]+[A-Z0-9/\-]+)?)",
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
       or dash). Among candidates we score by ``length × frequency`` because
       brand names get reprinted 5–15× on a typical pack while one-off
       codes (license numbers, batch ids) appear once.
    4. The longest capitalised alphabetic token (e.g. ``Cetirizine``),
       skipping obvious non-drug words.

    ``exclude`` lets callers pass in tokens that are *known* to be other
    fields (most importantly, the batch number). License-number tokens
    are auto-added to the exclusion set so an embossed code like
    ``ML24F-0043`` can't pose as a brand.
    """
    if brand_hint:
        return brand_hint
    if m := _GENERIC_NAME_RE.search(text):
        return m.group(1).strip(" .,").strip()

    excluded = {(e or "").upper() for e in (exclude or set())}
    excluded.discard("")
    if lic := _LIC_NO_RE.search(text):
        # Split the licence string on whitespace and '/' so each component
        # ("M/600/2012", "ML24F-0043/C", "ML24F", "0043", "C") gets banned
        # individually — that way a partial OCR of the same code can't
        # slip through either.
        for piece in re.split(r"[\s/]+", lic.group(1).upper()):
            if piece:
                excluded.add(piece)

    tokens = re.findall(r"\b[A-Z][A-Za-z0-9\-]{2,}\b", text)

    def _ok(tok: str) -> bool:
        return tok.lower() not in _STOPWORDS and tok.upper() not in excluded

    sku_like = [
        t for t in tokens if _ok(t) and (any(c.isdigit() for c in t) or "-" in t)
    ]
    if sku_like:
        freq = Counter(t.upper() for t in sku_like)
        return max(sku_like, key=lambda t: len(t) * freq[t.upper()])

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


def _squash(s: str) -> str:
    """Strip whitespace and uppercase — used for fields where layout drift
    (extra spaces, casing) shouldn't be treated as a content difference.
    """
    return re.sub(r"\s+", "", s).upper()


def _best_code_score(a: str, b: str) -> float:
    """Best of plain ``ratio`` and ``partial_ratio`` after squashing.

    ``partial_ratio`` rescues prefix/suffix drift ("ABC123" vs "X-ABC123")
    while ``ratio`` rescues single-character drops in the middle
    ("DBS3975" vs "DOBS3975"). Taking the max means we tolerate either
    failure mode without manually picking which one applies per field.
    """
    a_s, b_s = _squash(a), _squash(b)
    return max(fuzz.ratio(a_s, b_s), fuzz.partial_ratio(a_s, b_s))


# Per-field scorer table. Each scorer returns a 0–100 ratio.
#   - batch / drug_name use ``_best_code_score`` to absorb the two common
#     OCR drift patterns (interior char drops, edge prefix/suffix tweaks)
#     plus casing/punctuation drift via the squash step.
#   - dates / brand_name use plain ``ratio`` after squashing — they're
#     short atomic codes where a missing char *should* lower the score.
#   - Long descriptive fields fall through to ``token_set_ratio`` (default)
#     because real cases involve reordered/abbreviated words, e.g.
#     "MICRO LABS LIMITED" vs "MICROLABS LIMITED".
_FIELD_SCORERS: dict[str, Any] = {
    "batch":      _best_code_score,
    "drug_name":  _best_code_score,
    "brand_name": lambda a, b: fuzz.ratio(_squash(a), _squash(b)),
    "mfg_date":   lambda a, b: fuzz.ratio(_squash(a), _squash(b)),
    "exp_date":   lambda a, b: fuzz.ratio(_squash(a), _squash(b)),
}


def _default_scorer(a: str, b: str) -> float:
    return fuzz.token_set_ratio(a, b)


def _compare(label: dict[str, str], page: dict[str, str]) -> tuple[float, list[str]]:
    """Fuzzy-compare overlapping fields. Returns (mean_ratio_0_to_1, evidence).

    Scoring is per-field via :data:`_FIELD_SCORERS`; see that table for the
    rationale behind each choice. The default scorer is
    ``token_set_ratio`` for descriptive fields (manufacturer, generic name).
    """
    shared = sorted(set(label) & set(page))
    if not shared:
        return 0.0, []

    ratios: list[float] = []
    evidence: list[str] = []
    for key in shared:
        scorer = _FIELD_SCORERS.get(key, _default_scorer)
        ratio = scorer(label[key], page[key]) / 100.0
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
