"""Tests for ``services.grocery.claims``.

The vague-claim scanner walks a curated regex list (`VAGUE_CLAIMS`) and
emits one finding per *distinct* claim. Two pieces of the logic are
worth pinning down with focused tests:

- ``natural`` is filtered against a regulatory-context window so the
  scanner doesn't false-fire on FSSAI-mandated phrases like
  "added flavour (natural & nature identical flavouring substances)".
- ``multigrain`` is suppressed when the ingredients block confirms the
  product is actually whole grain.

The regression cases live in :mod:`backend.tests.test_grocery_real_world`;
this file holds the synthetic, surgical cases that are easier to reason
about when the regex changes.
"""

from __future__ import annotations

from app.schemas.status import StatusCode
from services.grocery.claims import find_vague_claims


def test_marketing_natural_fires() -> None:
    """A bare 'all natural' claim with no flavour/colour context fires."""
    findings = find_vague_claims("All natural ingredients!")
    codes = [f.code for f in findings]
    assert StatusCode.VAGUE_CLAIM_NATURAL in codes


def test_natural_flavouring_does_not_fire() -> None:
    """Regulatory phrasing about the *type* of flavouring used is a
    legal disclosure, not a marketing claim — must be skipped."""
    findings = find_vague_claims(
        "ADDED FLAVOUR (NATURAL & NATURE IDENTICAL FLAVOURING SUBSTANCES). "
        "Used as natural flavouring agent."
    )
    codes = [f.code for f in findings]
    assert StatusCode.VAGUE_CLAIM_NATURAL not in codes


def test_natural_colour_does_not_fire() -> None:
    """Same rule applies for colourants."""
    findings = find_vague_claims("Contains natural colour (turmeric extract).")
    codes = [f.code for f in findings]
    assert StatusCode.VAGUE_CLAIM_NATURAL not in codes


def test_natural_falls_through_to_marketing_match_when_both_present() -> None:
    """If a label has both regulatory and marketing uses of 'natural',
    we still flag the marketing one — the scanner walks every match
    until it finds non-regulatory context."""
    findings = find_vague_claims(
        "Used as natural flavouring agent. "
        "Made with 100% natural farm produce!"
    )
    codes = [f.code for f in findings]
    assert StatusCode.VAGUE_CLAIM_NATURAL in codes


def test_no_preservatives_fires() -> None:
    findings = find_vague_claims("No preservatives added")
    codes = [f.code for f in findings]
    assert StatusCode.VAGUE_CLAIM_NO_PRESERVATIVES in codes


def test_multigrain_fires_when_ingredients_lack_whole_grain() -> None:
    findings = find_vague_claims(
        "Multigrain Bread",
        ingredients_block="Refined wheat flour, water, sugar, yeast.",
    )
    codes = [f.code for f in findings]
    assert StatusCode.MULTIGRAIN_NOT_WHOLE in codes


def test_multigrain_suppressed_when_ingredients_have_whole_grain() -> None:
    findings = find_vague_claims(
        "Multigrain Bread",
        ingredients_block="Whole wheat flour, water, salt.",
    )
    codes = [f.code for f in findings]
    assert StatusCode.MULTIGRAIN_NOT_WHOLE not in codes


def test_each_claim_fires_only_once() -> None:
    """Repeating 'natural' three times should still produce a single
    VAGUE_CLAIM_NATURAL finding — duplicates clutter the timeline
    without adding signal."""
    findings = find_vague_claims("All natural. Truly natural. Natural goodness.")
    codes = [f.code for f in findings]
    assert codes.count(StatusCode.VAGUE_CLAIM_NATURAL) == 1


def test_empty_text_returns_empty_findings() -> None:
    assert find_vague_claims("") == []
    assert find_vague_claims(None) == []  # type: ignore[arg-type]
