"""Pure-function tests for the matcher.

These cover the bits the user actually cares about — field extraction and the
fuzzy comparison — without touching pytesseract, playwright, or Gemini. They
run in milliseconds and stay green even on a machine with no system deps.
"""

from __future__ import annotations

import pytest

from services.matcher.engine import _compare, _extract_fields, _pick_drug_name, match


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


# --- Real-world LABEL OCR fixture --------------------------------------------
#
# Captured verbatim from a Gemini OCR pass on the Dolo-650 blister photo
# (`backend/tests/fixtures/dolo_650_blister.jpg`). The label contains *both*
# "Mfg. Lic. No. M/600/2012 ML24F-0043/C" and the actual "MFG. MAR. 2023" —
# the matcher used to confuse the two and pick "LIC. NO" as the mfg date and
# "ML24F-0043" as the drug name. This fixture locks the fix in.
_DOLO_LABEL_TEXT = """
Dolo-650
Dosage - As directed by the Physician.
"Over dose may be injurious to Liver"
WARNING: Taking Paracetamol more than daily
dose may cause serious liver damage or allergic
reactions (e.g. swelling of the face, mouth and
throat, difficulty in breathing, itching or rash).
Mfg. Lic. No. M/600/2012 ML24F-0043/C
Made in India by:
MICRO LABS LIMITED
Mamring, Namthang Road,
Namchi-737 132, Sikkim.
Regd. Trade Mark
Dolo-650
Paracetamol Tablets IP
Dolo-650
Each uncoated tablet contains :
Paracetamol I.P. 650 mg.
Store in a cool & dark place,
Temperature not exceeding 30 C.
As directed by the Physician.
"Over dose may be injurious to Liver"
Dolo-650
Dolo-650
Dolo-650
Dolo-650
Dolo-650
MICRO LABS
B. No. DBS3975
MFG. MAR. 2023
EXP. FEB. 2029
M.R.P. FOR 15 TABS.
RS. 33.76 INCL. OF ALL TAXES
"""


def test_extract_fields_from_dolo_label_text() -> None:
    """Regression: with the old regex, mfg_date came back 'LIC. NO' and
    drug_name came back 'ML24F-0043'. Both should now be the real values."""
    fields = _extract_fields(_DOLO_LABEL_TEXT)

    assert fields["batch"] == "DBS3975"
    assert fields["mfg_date"] == "MAR. 2023"
    assert fields["exp_date"] == "FEB. 2029"
    # Frequency-weighted picker should beat the longest-token heuristic and
    # also skip the licence-code tokens added to the exclusion set.
    assert fields["drug_name"] == "Dolo-650"


def test_pick_drug_name_skips_license_codes() -> None:
    """A synthetic minimal repro: licence codes appear once, brand appears
    repeatedly. Without the licence-token exclusion + frequency weighting,
    the longest-token rule returns 'ML24F-0043' (10 chars) over 'Dolo-650'."""
    text = """
    Mfg. Lic. No. M/600/2012 ML24F-0043/C
    Dolo-650 Paracetamol Tablets IP
    Dolo-650 Dolo-650 Dolo-650
    """
    assert _pick_drug_name(text, brand_hint=None) == "Dolo-650"


def test_compare_normalises_whitespace_in_dates() -> None:
    """'FEB. 2029' vs 'FEB.2029' is the same date — used to score 47% under
    token_set_ratio because the tokenisation differed."""
    score, _ = _compare({"exp_date": "FEB. 2029"}, {"exp_date": "FEB.2029"})
    assert score >= 0.95


def test_compare_absorbs_batch_prefix_drift() -> None:
    """OCR sometimes captures the 'B. No.' prefix as part of the batch
    string ('B-ABC123' vs the page's 'ABC123'). partial_ratio inside the
    new scorer should treat that as a match instead of a 70% drop."""
    score, _ = _compare({"batch": "B-ABC123"}, {"batch": "ABC123"})
    assert score >= 0.95


def test_compare_keeps_real_world_dolo_batch_above_caution() -> None:
    """The exact failure case from prod: OCR dropped the 'O' in 'DOBS3975'.
    Plain ``ratio`` already scores this ~93%, well above the 80% safe-bar,
    so the field shouldn't pull the overall mean into 'caution' on its own."""
    score, _ = _compare({"batch": "DBS3975"}, {"batch": "DOBS3975"})
    assert score >= 0.90


@pytest.mark.asyncio
async def test_match_safe_for_dolo_real_world_payload() -> None:
    """Full pipeline against the exact label OCR + portal page from prod.
    Used to return verdict='high_risk', score=5. Should now be 'safe'."""
    page = {"title": "ACG", "visible_text": _DOLO_PAGE_TEXT}
    verdict = await match(
        barcode_payload="https://mlprd.mllqrv1.in/U/aaaabdib6i",
        ocr_text=_DOLO_LABEL_TEXT,
        scrape_data=page,
    )

    assert verdict.verdict == "safe", (
        f"expected 'safe', got {verdict.verdict!r} "
        f"(score={verdict.score}, evidence={verdict.evidence})"
    )
    assert verdict.score >= 8
