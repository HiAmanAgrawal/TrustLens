"""Tests for ``services.grocery.dates``.

Runs in milliseconds — no I/O, no Playwright. The fixtures are crafted
so that the date evaluator's three rules (expired / expires-soon /
mfg-old-long-shelf-life) each fire in isolation.
"""

from __future__ import annotations

from datetime import datetime

from app.schemas.status import StatusCode
from services.grocery.dates import evaluate_dates, extract_grocery_dates


_NOW = datetime(2026, 4, 23)


def test_extract_picks_up_each_date_keyword() -> None:
    text = """
    Mfg Date: 12/2024
    Best Before: 06/2027
    Use By: 31-DEC-2030
    """
    dates = extract_grocery_dates(text)

    assert dates["mfg"]
    assert dates["best_before"]
    assert dates["use_by"]


def test_extract_handles_indian_label_shorthand() -> None:
    text = """
    Manufactured on: APR.2025
    BB: 12 OCT 2026
    """
    dates = extract_grocery_dates(text)

    assert "mfg" in dates
    assert "best_before" in dates


def test_evaluate_flags_expired_use_by() -> None:
    dates = {"use_by": "31/12/2024", "mfg": "01/2024"}
    findings = evaluate_dates(dates, now=_NOW)

    codes = [f.code for f in findings]
    assert StatusCode.EXPIRED in codes


def test_evaluate_flags_expires_soon_within_30_days() -> None:
    dates = {"exp": "15/05/2026", "mfg": "01/2025"}
    findings = evaluate_dates(dates, now=_NOW)

    codes = [f.code for f in findings]
    assert StatusCode.EXPIRES_SOON in codes
    assert StatusCode.EXPIRED not in codes


def test_evaluate_flags_missing_mfg() -> None:
    dates = {"exp": "12/2030"}
    findings = evaluate_dates(dates, now=_NOW)

    codes = [f.code for f in findings]
    assert StatusCode.MFG_DATE_MISSING in codes


def test_evaluate_flags_old_mfg_with_long_shelf_life() -> None:
    """Manufactured > 12 months ago AND expiry > 18 months from MFG ⇒ flag."""
    dates = {"mfg": "01/2024", "exp": "12/2027"}
    findings = evaluate_dates(dates, now=_NOW)

    codes = [f.code for f in findings]
    assert StatusCode.MFG_OLD_LONG_SHELF_LIFE in codes


def test_evaluate_skips_old_mfg_when_short_shelf_life() -> None:
    """Old MFG but short shelf life shouldn't fire — that's normal for fresh foods."""
    dates = {"mfg": "01/2024", "exp": "06/2024"}
    findings = evaluate_dates(dates, now=_NOW)

    codes = [f.code for f in findings]
    assert StatusCode.MFG_OLD_LONG_SHELF_LIFE not in codes


def test_evaluate_with_no_dates_only_flags_missing_mfg() -> None:
    findings = evaluate_dates({}, now=_NOW)
    codes = [f.code for f in findings]
    assert codes == [StatusCode.MFG_DATE_MISSING]


def test_use_by_takes_priority_over_best_before_for_expiry() -> None:
    """If both are present, USE BY (safety) is the primary expiry signal."""
    dates = {
        "use_by": "01/01/2025",        # already past
        "best_before": "01/01/2030",   # in future
        "mfg": "01/2024",
    }
    findings = evaluate_dates(dates, now=_NOW)
    assert any(f.code == StatusCode.EXPIRED for f in findings)


def test_extract_synthesises_best_before_from_relative_shelf_life() -> None:
    """`Best Before N months from manufacture` → compute MFG + N months
    so the evaluator can reason about expiry just like an explicit date."""
    text = """
    MFG: 22 MAR 2025
    Best Before 4 months from manufacture.
    """
    dates = extract_grocery_dates(text)

    assert "mfg" in dates
    assert "best_before" in dates
    # Sanity-check the synthesised string is a real date the evaluator
    # can parse: MFG March + 4 months ≈ July 2025.
    assert "2025" in dates["best_before"]


def test_relative_best_before_marks_expired_when_mfg_is_old() -> None:
    """Synthesised best_before should drive EXPIRED when MFG + N months
    has already elapsed — the typical case for found-on-shelf old snacks."""
    text = """
    MFG: 22 MAR 2015
    Best Before 4 months from manufacture
    """
    dates = extract_grocery_dates(text)
    findings = evaluate_dates(dates, now=_NOW)
    codes = [f.code for f in findings]

    assert StatusCode.EXPIRED in codes


def test_extract_handles_pkd_keyword() -> None:
    """`PKD` (packed) is a less-common Indian variant of MFG/MFD — should
    still extract as a manufacturing date so we don't fire MFG_DATE_MISSING."""
    text = "PKD 03/2025"
    dates = extract_grocery_dates(text)
    assert "mfg" in dates
