# services/barcode/

Decode barcodes, QR codes, and DataMatrix codes **from an image**.

> If the user already has the decoded string (typed it, or pasted a URL
> containing a batch number), this package is bypassed entirely — the route
> hands the string straight to `services/matcher`. See [`POST /codes`](../../backend/README.md#endpoints-planned).

## Why a separate package from `ocr/`

OCR is fuzzy — barcode decoding is exact. The libraries, error modes, and
performance characteristics are completely different, so they earn their own
namespace.

## Stack

- **`pyzbar`** — covers EAN-13, UPC, Code128, QR. Needs the system library
  `libzbar0` (Linux) or `brew install zbar` (macOS).
- **`pylibdmtx`** (later) — DataMatrix codes used on pharma packs.
- **`pillow`** — image loading + pre-processing.

## Public API (intent)

```python
from services.barcode.decoder import decode

result = decode(image_bytes)
```

## Notes

- Photo barcodes from a phone are often blurry / skewed. Try multiple
  rotations (0°, 90°, 180°, 270°) before giving up.
- Some Indian pharma packs use DataMatrix, not QR — a single decoder won't
  cover both.
