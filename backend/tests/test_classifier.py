"""Tests for ``services.classifier``."""

from __future__ import annotations

from services.classifier import classify


_PHARMA_LABEL = """
Paracetamol Tablets IP
Mfg. Lic. No. M/600/2012
Schedule G drug. To be sold by retail on the prescription of a Registered
Medical Practitioner only.
Dosage: As directed by the Physician.
Each uncoated tablet contains Paracetamol 650 mg.
"""

_GROCERY_LABEL = """
Crispy Cookies — Rich in Taste
NUTRITION INFORMATION (per 100 g)
Energy 450 kcal
Sodium 750 mg
Ingredients: Refined wheat flour, sugar, edible vegetable oil, salt.
Best Before 12 months from Mfg date.
Contains: Wheat, Soy.
FSSAI Lic No: 12345678901234
Net Weight: 200 g
"""


def test_pharma_label_classifies_as_pharma() -> None:
    assert classify(
        barcode_payload=None,
        barcode_symbology="QRCODE",
        ocr_text=_PHARMA_LABEL,
    ) == "pharma"


def test_grocery_label_classifies_as_grocery() -> None:
    assert classify(
        barcode_payload="08901302207789",
        barcode_symbology="EAN13",
        ocr_text=_GROCERY_LABEL,
    ) == "grocery"


def test_pharma_verification_url_dominates_when_text_is_thin() -> None:
    """A QR pointing at the manufacturer-verification host is decisive even
    if the OCR text is too poor to score."""
    assert classify(
        barcode_payload="https://mlprd.mllqrv1.in/U/aaaabdib6i",
        barcode_symbology="QRCODE",
        ocr_text="some unreadable text",
    ) == "pharma"


def test_ean13_alone_doesnt_force_grocery_against_pharma_text() -> None:
    """A grocery-style barcode + clearly pharma text should still be pharma."""
    assert classify(
        barcode_payload="08901302207789",
        barcode_symbology="EAN13",
        ocr_text=_PHARMA_LABEL,
    ) == "pharma"


def test_no_signals_returns_unknown() -> None:
    assert classify(
        barcode_payload=None,
        barcode_symbology=None,
        ocr_text=None,
    ) == "unknown"


def test_tied_signals_return_unknown() -> None:
    """Equal pharma + grocery scores ⇒ unknown (best-effort)."""
    text = "Tablets IP. FSSAI Lic No: 12345678901234"
    # 'tablets ip' = +1 pharma; 'fssai' = +1 grocery; tie ⇒ unknown.
    assert classify(
        barcode_payload=None,
        barcode_symbology=None,
        ocr_text=text,
    ) == "unknown"


def test_classifier_is_case_insensitive() -> None:
    assert classify(
        barcode_payload=None,
        barcode_symbology=None,
        ocr_text="NUTRITION INFORMATION INGREDIENTS: SUGAR, SALT NET WEIGHT: 100G FSSAI",
    ) == "grocery"
