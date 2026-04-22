"""Pure-function tests for the matcher.

These cover the bits the user actually cares about — field extraction and the
fuzzy comparison — without touching pytesseract, playwright, or Gemini. They
run in milliseconds and stay green even on a machine with no system deps.
"""

from __future__ import annotations

import pytest

from services.matcher.engine import _compare, _extract_fields, match


def test_extract_fields_pulls_common_pharma_label_pieces() -> None:
    text = """
    Cetirizine Tablets 10mg
    Batch No: ABC123
    Mfg Date: 01/2024
    Exp Date: 12/2026
    Manufactured by: Acme Pharma Pvt. Ltd.
    """
    fields = _extract_fields(text)

    assert fields["batch"] == "ABC123"
    assert fields["mfg_date"] == "01/2024"
    assert fields["exp_date"] == "12/2026"
    assert "Acme Pharma" in fields["manufacturer"]
    assert fields["drug_name"] == "Cetirizine"


def test_extract_fields_returns_empty_for_blank() -> None:
    assert _extract_fields(None) == {}
    assert _extract_fields("") == {}


def test_compare_returns_zero_when_no_overlap() -> None:
    score, evidence = _compare({"batch": "X"}, {"manufacturer": "Y"})
    assert score == 0.0
    assert evidence == []


def test_compare_perfect_match_scores_one() -> None:
    score, evidence = _compare(
        {"batch": "ABC123", "drug_name": "Cetirizine"},
        {"batch": "ABC123", "drug_name": "Cetirizine"},
    )
    assert score == pytest.approx(1.0)
    assert len(evidence) == 2


@pytest.mark.asyncio
async def test_match_safe_when_label_and_page_agree() -> None:
    label = "Cetirizine 10mg Batch: ABC123 Mfg: 01/2024 Exp: 12/2026"
    page = {
        "title": "Acme Pharma — Verify",
        "visible_text": "Cetirizine Tablets 10mg Batch: ABC123 Mfg: 01/2024 Exp: 12/2026",
    }
    verdict = await match(barcode_payload="https://acme/v?b=ABC123", ocr_text=label, scrape_data=page)

    assert verdict.verdict == "safe"
    assert verdict.score >= 8
    assert any("batch" in e for e in verdict.evidence)


@pytest.mark.asyncio
async def test_match_high_risk_when_fields_disagree() -> None:
    label = "Paracetamol 500mg Batch: ABC123"
    page = {"title": "X", "visible_text": "Cetirizine Batch: ZZZ999"}
    verdict = await match(barcode_payload=None, ocr_text=label, scrape_data=page)

    assert verdict.verdict == "high_risk"
    assert verdict.score <= 4


@pytest.mark.asyncio
async def test_match_unverifiable_when_one_side_missing() -> None:
    verdict = await match(
        barcode_payload="ABC123", ocr_text="Cetirizine 10mg Batch: ABC123", scrape_data=None
    )
    assert verdict.verdict == "unverifiable"


# --- Real-world portal text fixtures ----------------------------------------
#
# These two cases come from actual scraped pages we hit in dev. Locking them
# in as tests means future refactors can't silently regress field extraction
# on the formats users actually send us.

_DOLO_PAGE_TEXT = """
Valid
DOLO-650

Each uncoated tablet contains Paracetamol IP 650 mg.

Unique product identification code:
08901302207789
Proper and Generic name of the drug:
Paracetamol Tablets IP
Name and Address of the manufacturer:
MICROLABS LIMITED

MAMRING NAMTHANG ROAD
NAMCHI
SIKKIM - 737132
India
Date of manufacturing:
MAR.2025
Date of expiry:
FEB.2029
Batch number:
DOBS3975
Brand Name:
DOLO-650
Manufacturing license number:
M/600/2012
"""

_SINAREST_LABEL_TEXT = """
B. NO. 7250293
MFG. DT. MAY 25
EXP. DT. APR. 28
Manufactured by: CENTAUR PHARMACEUTICALS PVT. LTD.
Sinarest
"""


def test_extract_fields_from_dolo_portal_page() -> None:
    fields = _extract_fields(_DOLO_PAGE_TEXT)
    assert fields["batch"] == "DOBS3975"
    assert fields["mfg_date"] == "MAR.2025"
    assert fields["exp_date"] == "FEB.2029"
    assert "MICROLABS LIMITED" in fields["manufacturer"].upper()
    assert fields["brand_name"] == "DOLO-650"
    # Brand name takes priority over the longest-token heuristic, so we get
    # the actual product name rather than "Manufacturing".
    assert fields["drug_name"] == "DOLO-650"


def test_extract_fields_from_sinarest_label() -> None:
    fields = _extract_fields(_SINAREST_LABEL_TEXT)
    assert fields["batch"] == "7250293"
    # Date capture must keep the space-and-year ("MAY 25", not just "MAY").
    assert fields["mfg_date"] == "MAY 25"
    assert fields["exp_date"] == "APR. 28"
    assert "CENTAUR" in fields["manufacturer"].upper()
    assert fields["drug_name"] == "Sinarest"


@pytest.mark.asyncio
async def test_match_safe_against_real_portal_text() -> None:
    """End-to-end: a label that genuinely matches the DOLO-650 portal page."""
    label = "DOLO-650 Paracetamol Tablets IP Batch: DOBS3975 Mfg: MAR.2025 Exp: FEB.2029"
    page = {"title": "ACG", "visible_text": _DOLO_PAGE_TEXT}
    verdict = await match(
        barcode_payload="https://mlprd.mllqrv1.in/U/abc",
        ocr_text=label,
        scrape_data=page,
    )
    assert verdict.verdict == "safe"
    assert verdict.score >= 8
    # Should compare batch + dates + drug_name, all from real-world text.
    keys_compared = {e.split(":", 1)[0] for e in verdict.evidence}
    assert "batch" in keys_compared
    assert "drug_name" in keys_compared
