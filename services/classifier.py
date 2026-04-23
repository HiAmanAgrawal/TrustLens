"""Item-category classifier (pharma vs grocery vs unknown).

Pure, fast, no I/O. Combines two signals:

* OCR keyword presence ("Tablets IP" → pharma; "Nutrition Information" →
  grocery). Each match adds 1 to that side's score.
* Barcode hints — manufacturer-portal hostnames in QR payloads are a
  strong pharma signal; consumer-grade EAN-13 / UPC symbologies are a
  weak grocery signal.

Ties (and ambiguous low scores) collapse to ``"unknown"``. The pipeline
defaults that to a best-effort path so the caller always gets a sensible
shape back.

Adding a keyword should never break an existing classification — at
worst it shifts a marginal case across the boundary, which is what we
want when the catalogue improves.
"""

from __future__ import annotations

from typing import Final

from app.schemas.grocery import Category

PHARMA_KEYWORDS: Final[tuple[str, ...]] = (
    "tablets ip",
    "tablet ip",
    "capsules ip",
    "capsule ip",
    "syrup ip",
    "mfg. lic.",
    "mfg lic",
    "manufacturing licence",
    "manufacturing license",
    "schedule g",
    "schedule h",
    "prescription drug",
    "prescription only",
    "physician",
    "dosage",
    "as directed by the physician",
    "registered medical practitioner",
    "paracetamol",
    "ibuprofen",
    "amoxicillin",
    "antibiotic",
    "mg.",
)

GROCERY_KEYWORDS: Final[tuple[str, ...]] = (
    "fssai",
    "nutrition information",
    "nutritional information",
    "nutritional facts",
    "nutrition facts",
    "ingredients:",
    "ingredients :",
    "best before",
    "use by",
    "net weight",
    "net wt",
    "per 100 g",
    "per 100g",
    "per 100ml",
    "per 100 ml",
    "per serving",
    "contains:",
    "veg.",
    "non-veg.",
    "vegetarian",
    "non vegetarian",
)

# Hostnames common to Indian pharma manufacturer-verification portals.
# Each match adds 3 to the pharma side — a single hit is decisive.
PHARMA_HOSTS: Final[tuple[str, ...]] = (
    "verify.",
    "mlprd.",
    "qrv1.",
    "mllqrv1",
    "centaurpharma",
    "microlabs",
    "abbott.",
    "cipla.",
    "sunpharma",
    "lupin.",
)

# Consumer-grade barcode symbologies — typical for grocery items at
# point-of-sale. Pharma packs use them too, but less consistently than
# they use the verification-QR pattern, so this is a weak +2 grocery hint.
_GROCERY_SYMBOLOGIES: Final[frozenset[str]] = frozenset(
    {"EAN13", "EAN8", "UPCA", "UPCE"}
)


def classify(
    *,
    barcode_payload: str | None,
    barcode_symbology: str | None,
    ocr_text: str | None,
) -> Category:
    """Decide whether to route this item to the pharma or grocery analyser.

    The decision is intentionally lossy — we only commit to a category
    when the evidence is asymmetric. ``"unknown"`` is the safe default
    for ambiguous cases; the pipeline still runs the pharma matcher in
    that case, but tags the response so a UI can show "we weren't sure".
    """
    text = (ocr_text or "").lower()

    pharma_score = sum(1 for kw in PHARMA_KEYWORDS if kw in text)
    grocery_score = sum(1 for kw in GROCERY_KEYWORDS if kw in text)

    if barcode_payload:
        payload_lc = barcode_payload.lower()
        if any(host in payload_lc for host in PHARMA_HOSTS):
            pharma_score += 3

    if barcode_symbology:
        normal = barcode_symbology.upper().replace("-", "").replace("_", "")
        if normal in _GROCERY_SYMBOLOGIES:
            grocery_score += 2

    if pharma_score == 0 and grocery_score == 0:
        return "unknown"

    if grocery_score > pharma_score:
        return "grocery"
    if pharma_score > grocery_score:
        return "pharma"

    # Tied with non-zero signals on both sides — best-effort.
    return "unknown"
