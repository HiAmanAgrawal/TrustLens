"""Ingredient-block extraction + analysis.

Two passes:

1. Find the "Ingredients:" block. Most labels list ingredients as a
   single comma-separated paragraph; we capture from the keyword up to
   the next obvious section break, the next ALL-CAPS heading, or the end
   of text. OCR'd labels often arrive as one long line with no blank-line
   separators, so the stoppers must work against inline keywords too.
2. Walk the captured block looking for hidden sugars, concerning E-codes,
   and allergen declarations. Counts of distinct items are surfaced so
   the caller can apply the "long ingredient list = heavily processed"
   heuristic separately.

The block extractor is forgiving — labels write "Ingredients", "INGREDIENTS",
"Ingredients (in order of weight):", or stick the list right under a
"Composition:" heading. Each variant gets a small alternation rather
than a single mega-regex.
"""

from __future__ import annotations

import re
from typing import Final

from app.schemas.grocery import Finding
from app.schemas.status import MESSAGES, StatusCode, _DEFAULT_SEVERITY

from ._data import (
    ALLERGENS,
    CONCERNING_E_CODES,
    HIDDEN_SUGAR_NAMES,
    HIDDEN_SUGARS_THRESHOLD,
    MANY_INGREDIENTS_THRESHOLD,
)

_BLOCK_HEADERS_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:ingredients?|composition|contents)\b\s*"
    r"(?:\([^)]*\))?\s*[:\-]\s*",
    re.IGNORECASE,
)

# Stop conditions: a blank line *or* any of the obvious post-ingredient
# section keywords appearing inline (real-world OCR collapses tables and
# paragraphs onto one line, so blank-line stoppers alone aren't enough).
# The keyword list is intentionally generous — false positives just shorten
# the block, which is far less harmful than swallowing manufacturer
# addresses, regulatory notices, and contact details into "ingredients".
_BLOCK_STOPPERS_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:\n\s*\n)"
    r"|\b(?:"
    # Section headings that typically follow ingredients.
    r"nutrition(?:al)?|allerge[ny]|storage|store\s+in|"
    r"net\s*(?:weight|wt|qty|quantity)|"
    r"best\s*before|use\s*by|"
    # Manufacturing / regulatory blocks.
    r"mfg\s*(?:by|date|dt|lic)|mfd\s*(?:by|date|dt)|"
    r"manufactur(?:ed|er|ing)|"
    r"marketed\s*by|mktd\.?\s*by|"
    r"made\s+in|distributed\s+by|imported\s+by|"
    # Contact / customer-care blocks.
    r"customer\s+care|consumer\s+(?:services?|feedback)|"
    r"for\s+(?:manufacturing|feedback|queries|complaints?|consumer)|"
    r"powered\s+by|"
    # Misc front-of-pack chrome that drifts into the block in busy OCR.
    r"contains?\s+added\s+(?:flavour|flavor|colour|color|preservative)|"
    r"proprietary\s+food|"
    r"regd\.?\s*trade\s*mark|registered\s+trade\s*mark|"
    # Regulatory IDs / URLs.
    r"fssai|lic\.?\s*no|licen[cs]e\s+no|"
    r"www\.|https?://|tel\.?\s*no|email\s*id|phone\s*no"
    r")\b",
    re.IGNORECASE,
)

# Hard cap on the captured block. Real ingredient lists almost never
# exceed ~400 chars; anything longer is OCR drift past the actual list.
_BLOCK_MAX_CHARS: Final[int] = 400

# Filters for ``_split_items`` — drop fragments that look like sentences,
# addresses, or company names (none of which are ingredients).
_NON_INGREDIENT_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^contains?\s+added", re.IGNORECASE),
    re.compile(r"^proprietary", re.IGNORECASE),
    re.compile(r"\b(?:pvt|ltd|limited|inc|corp)\.?\b", re.IGNORECASE),
    re.compile(r"\b(?:p\.?o\.?\s*box|pin\s*[:\-]?\s*\d)", re.IGNORECASE),
    re.compile(r"\bmkt\.?\s*by\b|\bmfd\.?\s*by\b|\bmf\.?\s*by\b", re.IGNORECASE),
    # Long "see panel below" / "for unit address" boilerplate sentences.
    re.compile(r"^(?:for|see|please|kindly)\b", re.IGNORECASE),
)
_MAX_ITEM_CHARS: Final[int] = 60

# A "Contains: …" style allergen declaration. Captures the trailing list
# so we can echo the matched allergens back as evidence.
_CONTAINS_RE: Final[re.Pattern[str]] = re.compile(
    r"\bcontains?\s*[:\-]\s*([^\n.;]+)",
    re.IGNORECASE,
)

# Generic E-code pattern. Allows the optional space ("E 102") and trailing
# letter ("E160a") common on European labels. Upper-cased before lookup.
_E_CODE_RE: Final[re.Pattern[str]] = re.compile(
    r"\bE\s?\d{3,4}[A-Z]?\b",
    re.IGNORECASE,
)


def extract_ingredients_block(text: str) -> str | None:
    """Return the comma-separated ingredient list, or ``None`` if not found.

    Stripped of the leading ``Ingredients:`` keyword and trimmed to the
    next obvious section break (or :data:`_BLOCK_MAX_CHARS`, whichever
    comes first). Returns ``None`` when no recognisable ingredients
    header is present.
    """
    if not text:
        return None

    header = _BLOCK_HEADERS_RE.search(text)
    if not header:
        return None

    after = text[header.end():]
    stop = _BLOCK_STOPPERS_RE.search(after)
    block = after[: stop.start()] if stop else after

    # Hard length cap. Walk back from the cap to the last ``.``/``;`` so
    # we don't end mid-ingredient on the rare label that legitimately runs
    # past the limit.
    if len(block) > _BLOCK_MAX_CHARS:
        truncated = block[:_BLOCK_MAX_CHARS]
        last_break = max(
            truncated.rfind("."),
            truncated.rfind(";"),
            truncated.rfind("\n"),
        )
        block = truncated[: last_break + 1] if last_break >= _BLOCK_MAX_CHARS // 2 else truncated

    block = block.strip()
    if not block:
        return None
    return block


def analyze_ingredients(block: str | None) -> tuple[list[Finding], int | None]:
    """Return (findings, ingredients_count) for the given ingredients block.

    ``block`` may be ``None`` (no ingredients header in OCR'd text); in
    that case both outputs are empty / ``None`` and the analyser caller
    decides whether to attach a ``MISSING`` note at the verdict level.
    """
    if not block:
        return [], None

    findings: list[Finding] = []

    items = _split_items(block)
    count = len(items) if items else None

    sugar_hits = _find_hidden_sugars(block)
    if len(sugar_hits) >= HIDDEN_SUGARS_THRESHOLD:
        findings.append(
            _finding(
                StatusCode.HIDDEN_SUGARS_FOUND,
                evidence=", ".join(sorted(sugar_hits)),
            )
        )

    e_hits = _find_concerning_e_codes(block)
    if e_hits:
        findings.append(
            _finding(
                StatusCode.CONCERNING_E_CODES,
                evidence=", ".join(sorted(e_hits)),
            )
        )

    if count is not None and count > MANY_INGREDIENTS_THRESHOLD:
        findings.append(
            _finding(
                StatusCode.MANY_INGREDIENTS,
                evidence=f"{count} ingredients",
            )
        )

    contains = _find_contains_line(block)
    if contains:
        findings.append(_finding(StatusCode.ALLERGEN_DECLARATION_FOUND, evidence=contains))
    else:
        # "Missing" is informational: the absence of a Contains: line is
        # only a problem if the actual ingredients include known allergens.
        if _block_mentions_allergen(block):
            findings.append(_finding(StatusCode.ALLERGEN_DECLARATION_MISSING))

    return findings, count


def _split_items(block: str) -> list[str]:
    """Split an ingredients block on commas / semicolons and filter noise.

    Parens (sub-ingredient breakdowns like ``Maida (refined wheat flour)``)
    are kept intact — splitting inside them would inflate the count.
    Items longer than :data:`_MAX_ITEM_CHARS` or matching any
    :data:`_NON_INGREDIENT_PATTERNS` (company names, addresses, sentence
    fragments) are dropped: those are OCR drift, not ingredients.
    """
    raw: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in block:
        if ch in "([{":
            depth += 1
            cur.append(ch)
            continue
        if ch in ")]}":
            depth = max(depth - 1, 0)
            cur.append(ch)
            continue
        if ch in ",;\n" and depth == 0:
            piece = "".join(cur).strip(" .\t'\"")
            if piece:
                raw.append(piece)
            cur = []
            continue
        cur.append(ch)
    tail = "".join(cur).strip(" .\t'\"")
    if tail:
        raw.append(tail)
    return [item for item in raw if _is_ingredient_like(item)]


def _is_ingredient_like(item: str) -> bool:
    """True iff ``item`` plausibly names a single ingredient.

    Filters out long sentences, company names ("PEPSICO INDIA HOLDINGS PVT LTD"),
    addresses ("PIN: 148026"), and boilerplate phrases ("CONTAINS ADDED…",
    "PROPRIETARY FOOD") that the block extractor sometimes can't fully
    exclude when the OCR is one long line of text.
    """
    if not item or len(item) > _MAX_ITEM_CHARS:
        return False
    return all(not pat.search(item) for pat in _NON_INGREDIENT_PATTERNS)


def _find_hidden_sugars(block: str) -> set[str]:
    """Return the set of distinct hidden-sugar names found in the block."""
    haystack = block.lower()
    return {name for name in HIDDEN_SUGAR_NAMES if _whole_word_in(name, haystack)}


def _whole_word_in(needle: str, haystack: str) -> bool:
    """Word-boundary substring match. Multi-word needles (``corn syrup``)
    still get whole-phrase matching this way without tripping on
    ``cornflour`` or ``syrupy``."""
    pattern = r"(?<!\w)" + re.escape(needle) + r"(?!\w)"
    return re.search(pattern, haystack) is not None


def _find_concerning_e_codes(block: str) -> set[str]:
    """Return the set of distinct concerning E-codes found in the block.

    The lookup is upper-cased and stripped of internal whitespace so
    ``E 102``, ``e102``, and ``E102`` all count as the same hit.
    """
    hits: set[str] = set()
    for raw in _E_CODE_RE.findall(block):
        normal = raw.replace(" ", "").upper()
        if normal in CONCERNING_E_CODES:
            hits.add(normal)
    return hits


def _find_contains_line(block: str) -> str | None:
    """Return the trailing list after a 'Contains:' allergen line, if any."""
    m = _CONTAINS_RE.search(block)
    if not m:
        return None
    listed = m.group(1).strip()
    return listed or None


def _block_mentions_allergen(block: str) -> bool:
    haystack = block.lower()
    return any(_whole_word_in(name, haystack) for name in ALLERGENS)


def _finding(code: StatusCode, *, evidence: str | None = None) -> Finding:
    return Finding(
        code=code,
        severity=_DEFAULT_SEVERITY.get(code, "info"),
        message=MESSAGES[code],
        evidence=evidence or None,
    )
