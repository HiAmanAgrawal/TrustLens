"""Tests for ``services.grocery.fssai``.

The Playwright-driven ``verify_online`` is exercised via a monkeypatched
result-parser fixture so we never hit the real FoSCoS portal in unit
tests. The format-only path runs for real — it's pure regex.
"""

from __future__ import annotations

import pytest

from app.schemas.grocery import FssaiCheck
from services.grocery import fssai


def test_extract_license_picks_up_keyworded_number() -> None:
    text = "Mfg. by ACME Foods. FSSAI Lic. No: 12345678901234"
    assert fssai.extract_license(text) == "12345678901234"


def test_extract_license_returns_none_when_not_present() -> None:
    text = "No license printed on this label."
    assert fssai.extract_license(text) is None


def test_extract_license_avoids_random_14_digit_runs() -> None:
    """A 14-digit GTIN with no FSSAI keyword shouldn't be claimed as a license."""
    text = "EAN: 89060131468460. Made in India."
    assert fssai.extract_license(text) is None


def test_extract_license_returns_bare_run_when_fssai_mentioned() -> None:
    """If 'FSSAI' is on the label but not adjacent to the number, fall back
    to any bare 14-digit run — better than missing it entirely."""
    text = "Powered by FSSAI guidelines.\n\nLicense 12345678901234"
    assert fssai.extract_license(text) == "12345678901234"


def test_validate_format_accepts_valid_state_code() -> None:
    assert fssai.validate_format("12345678901234") is True
    assert fssai.validate_format("21345678901234") is True


def test_validate_format_rejects_wrong_length() -> None:
    assert fssai.validate_format("1234567890123") is False  # 13 digits
    assert fssai.validate_format("123456789012345") is False  # 15 digits


def test_validate_format_rejects_non_digit() -> None:
    assert fssai.validate_format("1234ABCD901234") is False


def test_validate_format_rejects_invalid_first_digit() -> None:
    """Real licenses start with 1 or 2 (state code prefix)."""
    assert fssai.validate_format("32345678901234") is False
    assert fssai.validate_format("92345678901234") is False


def test_validate_format_rejects_none() -> None:
    assert fssai.validate_format(None) is False


@pytest.mark.asyncio
async def test_verify_online_skips_when_format_invalid() -> None:
    """Online lookup should never run for a malformed license — degrades gracefully."""
    check = await fssai.verify_online("0000")
    assert isinstance(check, FssaiCheck)
    assert check.format_valid is False
    assert check.online_status == "lookup_failed"
    assert check.verify_url == fssai.FSSAI_VERIFY_URL


@pytest.mark.asyncio
async def test_verify_online_degrades_when_browser_unavailable(monkeypatch) -> None:
    """No browser → return format-valid + lookup_failed, with verify_url."""
    async def boom():
        raise RuntimeError("no browser")

    monkeypatch.setattr(
        "services.scraper.agent._get_browser", boom
    )

    check = await fssai.verify_online("12345678901234")
    assert check.format_valid is True
    assert check.online_status == "lookup_failed"
    assert check.verify_url == fssai.FSSAI_VERIFY_URL


def test_parse_result_detects_no_record() -> None:
    html = "<html><body>no record found for this license</body></html>"
    check = fssai._parse_result(html.lower(), "12345678901234")
    assert check.online_status == "invalid"


def test_parse_result_detects_expired() -> None:
    html = "<html><body>this license is expired</body></html>"
    check = fssai._parse_result(html.lower(), "12345678901234")
    assert check.online_status == "expired"


def test_parse_result_detects_valid() -> None:
    html = "<html><body>license is valid and active</body></html>"
    check = fssai._parse_result(html.lower(), "12345678901234")
    assert check.online_status == "valid"


def test_extract_license_loosely_picks_up_13_digit_near_lic_keyword() -> None:
    """OCR routinely drops a digit from a 14-digit licence printed under a
    'Lic. No' label. Surface what we found so the caller can flag
    FSSAI_FORMAT_INVALID rather than reporting 'no license at all'."""
    text = "Maharashtra. Lic. No. 1012002000869"
    extracted = fssai.extract_license(text)
    assert extracted == "1012002000869"
    # The strict format check still rejects it (13 digits) — the calling
    # analyzer turns this into a FSSAI_FORMAT_INVALID finding.
    assert fssai.validate_format(extracted) is False


def test_extract_license_loose_path_requires_lic_anchor() -> None:
    """A bare 13-digit number with no nearby 'Lic' keyword must still
    return None — otherwise we'd accidentally pick up postal codes,
    phone numbers, or random GTIN fragments."""
    text = "Random number 1012002000869 in some marketing copy"
    assert fssai.extract_license(text) is None


def test_extract_license_loose_handles_15_digit_drift() -> None:
    """OCR can also duplicate a digit; 15 digits near 'Licence No.' should
    still be surfaced for the user to verify manually."""
    text = "Licence No. 100120020008690"
    assert fssai.extract_license(text) == "100120020008690"
