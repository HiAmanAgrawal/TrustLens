"""Real-world OCR regressions for the grocery analyser.

Each test pins a *specific* OCR transcription that previously produced a
poor analysis (phantom ingredients, missing FSSAI, missing nutrition
detection) and asserts the improved behaviour. Treat them as
characterisation tests: when the analyser changes, these are the labels
to manually re-eyeball.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.schemas.status import StatusCode
from services.grocery import analyzer as grocery_analyzer
from services.grocery.dates import extract_grocery_dates


# Real OCR output from a Lay's American Style Cream & Onion 25 g pack.
# Tesseract @ 0.6 confidence on a busy multilingual back-of-pack — the
# nutrition values, MFG date, and FSSAI numbers are present in the
# printed pack but mostly mangled in the transcription. We extract what
# we can and surface partial-table / format-invalid hints rather than
# claiming things are missing entirely.
_LAYS_OCR_TEXT = (
    "fa ieush past! Sit back, yglax and savoury the Magic of now with thy "
    "creamy irresistible tasie, —Y JWIRIIONAL INFORMATION (APPROX,: Per 100g "
    "\"net more than 0,1 percent by weight. «Santen 00k more than 16.1 per "
    "cent by weight, Find us on: facebook.com/laysindia S) * (hl, i) ie aot "
    "al taxes), lays [e] 4) 259 ezzos MARIS Mo, Rsio/ g og Lay's American "
    "Style Cream & Onion am (@B pal Banaye i\\\\,.// Lay'sis the Registered "
    "Trade Marko INGREDIENTS: Pao, Edible Veet Mik Produits Mik Sold, Cheese "
    "Fo. 'Spices & Condiments (Onion Pond Pepper Powder), larch CONTAINS "
    "ADDED FLAVOR\\ IDENTICAL FLAVOURING \"Used as natural flavouring aac "
    "\"PROPRIETARY FOOD\" For manufacturing unit address, see sti of batch "
    "no. and see below, 'Mf. By: PEPSICO INDIA HOLoNNs vr Mi Vilage Channo, "
    "Patiala - Sanu Ro 0 st Sano, Pin - 148026, Pui, i: N2:C-5, MIDG "
    "Ranjangaon, Talika Stns, Maharashtra Lio, No, 1012002000869 N3: JLo, 2 "
    "84 (Kendva Panchayat) Movi Wa And Moun, P.O, Ohulagarh, PS, Sani | Pin "
    "711802, West Bengal Lic No. 1012010 'Marketed by: PEPSICO INDIA "
    "HOLDINGS PV. 7. (Fito-Lay Division) 3-8, DLE Corporate Pak. S Block, "
    "Qutab Enclave, Phase: Gurgaon - 122002, Haryana, Far edck or ues ui The "
    "Consumer Services Manager, PEPSICO INDIA HOLDINGS PVT. LTD. (rv RO, Box "
    "27, DIF Qutab Enclave, Phase 1, Gurgaon - 122002, Haryana, Or call us "
    "at 1800.22 4020 Or email us at 'consumer.feedback@pepsico.co™ WN ag "
    "Lic Ha i"
)


@pytest.mark.asyncio
async def test_lays_ocr_no_longer_reports_27_phantom_ingredients() -> None:
    """Pre-fix: the block extractor swallowed the manufacturer address,
    contact info, and "PROPRIETARY FOOD" line, producing 27 'ingredients'.
    Post-fix: only the actual ingredient fragments survive."""
    report = await grocery_analyzer.analyze(_LAYS_OCR_TEXT, online_fssai=False)

    assert report.ingredients_count is not None
    # Real list is ~6 items; allow up to 10 for OCR splitting noise.
    assert 1 <= report.ingredients_count <= 10, (
        f"expected ≤10 ingredients, got {report.ingredients_count}"
    )

    finding_codes = [f.code for f in report.findings]
    assert StatusCode.MANY_INGREDIENTS not in finding_codes


@pytest.mark.asyncio
async def test_lays_ocr_surfaces_partial_nutrition_table() -> None:
    """The OCR has 'Per 100g' + 'percent by weight' but no readable rows.
    Pre-fix we said 'no nutrition table'. Post-fix we say 'partial table',
    which is a more honest signal to the consumer."""
    report = await grocery_analyzer.analyze(_LAYS_OCR_TEXT, online_fssai=False)

    finding_codes = [f.code for f in report.findings]
    assert StatusCode.NUTRITION_TABLE_PARTIAL in finding_codes
    assert StatusCode.NUTRITION_TABLE_MISSING not in finding_codes


@pytest.mark.asyncio
async def test_lays_ocr_surfaces_loose_fssai_license() -> None:
    """The OCR captured a 13-digit number (one digit dropped from the real
    14-digit licence) under 'Lic. No.'. Pre-fix we said 'no license found'.
    Post-fix we surface the captured digits as FSSAI_FORMAT_INVALID so the
    user can see we *found* something and verify manually."""
    report = await grocery_analyzer.analyze(_LAYS_OCR_TEXT, online_fssai=False)

    assert report.fssai is not None
    assert report.fssai.license_number is not None
    assert report.fssai.format_valid is False

    finding_codes = [f.code for f in report.findings]
    assert StatusCode.FSSAI_FORMAT_INVALID in finding_codes
    assert StatusCode.FSSAI_NOT_FOUND_ON_LABEL not in finding_codes


# Real OCR output from the *same* Lay's pack but transcribed by Gemini
# Vision (engine="gemini", confidence=0.9). The cloud OCR cleans up most
# of the mangled text — meaning the analyser now has to reason about a
# parseable bottom-of-pack stamp ("MFD: 22 MAR 15", "BEST BEFORE FOUR
# MONTHS FROM MANUFACTURE") and the regulatory phrase "(NATURAL & NATURE
# IDENTICAL FLAVOURING SUBSTANCES)". This is the corpus behind the
# user-reported "is this response quality good?" critique.
_LAYS_OCR_TEXT_GEMINI = (
    "Let the world rush past!\n"
    "Sit back, relax and savour\n"
    "the magic of now with the\n"
    "creamy irresistible taste of\n"
    "Lay's American Style\n"
    "Cream & Onion.\n\n"
    "Lay's Pal Banaye Magical\n\n"
    "Lay's is the Registered Trade Mark of Regd User\n"
    "INGREDIENTS: Potato, Edible Vegetable Oil, Sugar, Salt, "
    "Milk Products (Milk Solids, Cheese Powder), (1.4%)*\n"
    "*Spices & Condiments (Onion Powder, Parsley Powder,\n"
    "Pepper Powder), Starch.\n\n"
    "CONTAINS ADDED FLAVOUR (NATURAL & NATURE\n"
    "IDENTICAL FLAVOURING SUBSTANCES)\n"
    "*Used as natural flavouring agent.\n"
    "\"PROPRIETARY FOOD\"\n"
    "For manufacturing unit address, see first two characters\n"
    "of batch no. and see below.\n"
    "Mfd. By: PEPSICO INDIA HOLDINGS PVT. LTD. (Frito-Lay Division)\n"
    "N1: Village Channo, Patiala - Sangrur Road, P.O. Bhawanigarh,\n"
    "Distt. Sangrur, Pin - 148026, Punjab. Lic. No. 10012630000282\n"
    "N2: C-5, MIDC Ranjangaon, Taluka Shirur, Pune, Pin - 412220,\n"
    "Maharashtra. Lic. No. 10012022000339\n"
    "N3: JL no. 2 & 4 (Kendua Panchayat), Mouja Jadupur, Post\n"
    "via Andul Mouri, P.O. Dhulagarh, P.S. Sankrail, Distt. Howrah,\n"
    "Pin - 711302, West Bengal. Lic. No. 10012031000120\n\n"
    "Marketed by: PEPSICO INDIA HOLDINGS PVT. LTD.\n"
    "(Frito-Lay Division) 3-B, DLF Corporate Park,\n"
    "S Block, Qutab Enclave, Phase- III,\n"
    "Gurgaon - 122002, Haryana.\n"
    "Lic No. 10014040000079\n\n"
    "NUTRITIONAL INFORMATION (APPROX.):\n"
    "Per 100g\n"
    "Energy kcal 544\n"
    "Protein g 7.8\n"
    "Total Carbohydrate g 51.6\n"
    "d'which Sugars g 2.0\n"
    "Total Fat g 34.0\n"
    "Trans Fat content not more than 0.1 per cent by weight.\n"
    "Saturated Fat content not more than 16.1 per cent by weight.\n\n"
    "NQTY: 25g\n"
    "B.NO: NZ220315\n"
    "MFD: 22 MAR 15\n"
    "MRP: Rs.10/-\n"
    "81 days\n\n"
    "BEST BEFORE FOUR MONTHS FROM MANUFACTURE\n"
    "8 901491 503037"
)


# Pin "now" so the EXPIRED assertions don't drift over real time —
# this matches the user's observation date when they reported the bug.
_NOW = datetime(2026, 4, 23)


def test_lays_gemini_ocr_extracts_mfd_despite_earlier_manufacturing_mention() -> None:
    """The OCR mentions 'For manufacturing unit address' and 'Mfd. By:'
    *before* the actual stamp 'MFD: 22 MAR 15'. Pre-fix the keyword
    regex matched the first occurrence (no date there) and gave up,
    leaving us claiming 'no MFG date readable' on a pack that prints
    one in plain English."""
    dates = extract_grocery_dates(_LAYS_OCR_TEXT_GEMINI)

    assert "mfg" in dates
    assert "MAR" in dates["mfg"].upper()
    assert "15" in dates["mfg"]


def test_lays_gemini_ocr_synthesises_best_before_from_word_numeral() -> None:
    """The pack says 'BEST BEFORE FOUR MONTHS FROM MANUFACTURE' (word,
    not digit). Pre-fix the relative-shelf-life regex required digits
    and silently dropped the synthesis."""
    dates = extract_grocery_dates(_LAYS_OCR_TEXT_GEMINI)

    assert "best_before" in dates
    # MFG = March 2015 + 4 months ⇒ July 2015.
    assert "2015" in dates["best_before"]


@pytest.mark.asyncio
async def test_lays_gemini_ocr_flags_expired_pack() -> None:
    """End-to-end: the resulting analysis must mark this 11-year-old
    pack as EXPIRED (error severity → risk_band='high'). Anything less
    is a safety failure — the previous response said 'caution / medium'
    and never told the user the pack was years out of date."""
    report = await grocery_analyzer.analyze(
        _LAYS_OCR_TEXT_GEMINI,
        now=_NOW,
        online_fssai=False,
    )

    finding_codes = [f.code for f in report.findings]
    assert StatusCode.EXPIRED in finding_codes
    assert StatusCode.MFG_DATE_MISSING not in finding_codes
    assert report.risk_band == "high"


@pytest.mark.asyncio
async def test_lays_gemini_ocr_does_not_flag_regulated_natural_flavouring() -> None:
    """`(NATURAL & NATURE IDENTICAL FLAVOURING SUBSTANCES)` and
    `Used as natural flavouring agent` are FSSAI-mandated descriptors
    of the *type* of flavouring used — not vague marketing. Pre-fix the
    claim scanner fired on every 'natural' it saw, eroding consumer
    trust by crying wolf on a legal disclosure."""
    report = await grocery_analyzer.analyze(
        _LAYS_OCR_TEXT_GEMINI,
        now=_NOW,
        online_fssai=False,
    )

    finding_codes = [f.code for f in report.findings]
    assert StatusCode.VAGUE_CLAIM_NATURAL not in finding_codes
