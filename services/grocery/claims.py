"""Vague-marketing-claim detection.

Front-of-pack claims like "natural", "farm fresh", "no added preservatives"
have no legal definition in most jurisdictions, so they're a flag —
not a fault — to surface to the user. Each pattern in
:data:`._data.VAGUE_CLAIMS` maps to a ``StatusCode``; we also implement
one cross-field heuristic ("multigrain" without "whole grain" in the
ingredients) that needs both the OCR text and the parsed ingredients
block, so it lives here rather than next to the regex list.
"""

from __future__ import annotations

import re
from typing import Final

from app.schemas.grocery import Finding
from app.schemas.status import MESSAGES, StatusCode, _DEFAULT_SEVERITY

from ._data import VAGUE_CLAIMS

_CLAIM_TO_CODE: Final[dict[str, StatusCode]] = {
    "natural": StatusCode.VAGUE_CLAIM_NATURAL,
    "farm_fresh": StatusCode.VAGUE_CLAIM_NATURAL,
    "no_preservatives": StatusCode.VAGUE_CLAIM_NO_PRESERVATIVES,
    "low_fat": StatusCode.VAGUE_CLAIM_LOW_FAT,
    "multigrain": StatusCode.MULTIGRAIN_NOT_WHOLE,  # always flagged from this pass too
    "homestyle": StatusCode.VAGUE_CLAIM_NATURAL,
    "doctor_recommended": StatusCode.VAGUE_CLAIM_NATURAL,
}

_WHOLE_GRAIN_RE: Final[re.Pattern[str]] = re.compile(
    r"\bwhole\s*(?:wheat|grain)\b",
    re.IGNORECASE,
)

# Words that, if they appear in the same printed phrase as a matched
# "natural", indicate the word is functioning as a regulatory descriptor
# (FSSAI / Codex labelling language for added flavour or colour types)
# rather than as a marketing claim. Without this filter we'd false-fire
# on every snack pack that prints
# "ADDED FLAVOUR (NATURAL & NATURE IDENTICAL FLAVOURING SUBSTANCES)" —
# a legally required disclosure, not a marketing flourish.
_NATURAL_REGULATORY_CONTEXT: Final[re.Pattern[str]] = re.compile(
    r"\b(?:"
    r"flavou?r(?:ing|ings|ed)?|"
    r"colou?r(?:ing|ings|ed)?|"
    r"nature\s+identical|"
    r"flavou?ring\s+(?:agent|substance)s?|"
    r"colou?ring\s+(?:agent|substance)s?"
    r")\b",
    re.IGNORECASE,
)

# Sentence / phrase delimiters used to bound the regulatory-context
# check. Without them, "natural flavouring." in one sentence would
# poison the check for "100% natural" in the next.
_PHRASE_BOUNDARIES: Final[str] = ".;:\n"


def find_vague_claims(text: str, *, ingredients_block: str | None = None) -> list[Finding]:
    """Scan ``text`` for unregulated marketing claims.

    Each matched claim fires once even if the phrase appears multiple
    times. Two special cases:

    - ``multigrain``: suppressed when the ingredients block confirms
      the product is actually whole grain.
    - ``natural``: suppressed for every match whose surrounding text
      mentions ``flavour``/``colour``/``nature identical`` — those are
      regulatory descriptors of the type of flavouring or colouring
      used, not standalone health claims. We walk every occurrence of
      "natural" until we find one in non-regulatory context (or give up).
    """
    if not text:
        return []

    findings: list[Finding] = []
    seen_codes: set[StatusCode] = set()

    for label, pattern in VAGUE_CLAIMS:
        code = _CLAIM_TO_CODE.get(label)
        if code is None or code in seen_codes:
            continue

        if label == "natural":
            evidence = _first_marketing_natural(text, pattern)
            if evidence is None:
                continue
            findings.append(_finding(code, evidence=evidence))
            seen_codes.add(code)
            continue

        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue

        if label == "multigrain":
            if ingredients_block and _WHOLE_GRAIN_RE.search(ingredients_block):
                continue
            findings.append(_finding(code, evidence=m.group(0)))
            seen_codes.add(code)
            continue

        findings.append(_finding(code, evidence=m.group(0)))
        seen_codes.add(code)

    return findings


def _first_marketing_natural(text: str, pattern: str) -> str | None:
    """Return the first ``natural`` match that isn't a regulated descriptor.

    Each occurrence of ``natural`` is checked against the surrounding
    phrase — bounded by sentence punctuation so a regulatory mention in
    one sentence doesn't poison the check for a marketing mention in
    the next. If the phrase contains a regulatory keyword
    (``flavour``, ``colour``, ``nature identical``, …) the match is
    treated as a legal disclosure and skipped.
    """
    for m in re.finditer(pattern, text, re.IGNORECASE):
        phrase = _surrounding_phrase(text, m.start(), m.end())
        if _NATURAL_REGULATORY_CONTEXT.search(phrase):
            continue
        return m.group(0)
    return None


def _surrounding_phrase(text: str, start: int, end: int) -> str:
    """Return the substring of ``text`` containing ``[start, end)``,
    truncated at the nearest sentence/phrase boundary on each side.

    Phrase boundaries are :data:`_PHRASE_BOUNDARIES` characters; the
    returned string excludes the boundary itself so a trailing ``.``
    on the previous sentence doesn't show up in the regulatory check.
    """
    left = start
    while left > 0 and text[left - 1] not in _PHRASE_BOUNDARIES:
        left -= 1
    right = end
    while right < len(text) and text[right] not in _PHRASE_BOUNDARIES:
        right += 1
    return text[left:right]


def _finding(code: StatusCode, *, evidence: str | None = None) -> Finding:
    return Finding(
        code=code,
        severity=_DEFAULT_SEVERITY.get(code, "info"),
        message=MESSAGES[code],
        evidence=evidence or None,
    )
