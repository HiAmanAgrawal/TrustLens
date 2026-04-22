# services/matcher/

The brain. Takes whatever the barcode + OCR + scraper services produced and
turns it into a single, user-facing **verdict**: a 0–10 score plus a plain
language summary.

## Inputs

The matcher is the **convergence point for both input paths**:

- **Image path** — `barcode_payload` from `services/barcode`, `ocr_text` from `services/ocr`.
- **Code-text path** — the user typed the barcode / QR number directly (or pasted a URL containing a batch param). `barcode_payload` is set, `ocr_text` is `None`.

In all cases the matcher receives:

- A barcode payload string (may be `None` if the photo had only a label).
- OCR text (may be `None` for the code-text path or for barcode-only photos).
- Zero or more `ScrapeResult`s from manufacturer portals.
- Lookups against authoritative datasets: CDSCO DAVA, OpenFDA, DrugBank, PubChem.

## Output

A `Verdict` containing:

- `score` — 0 to 10.
- `verdict` — `"high_risk" | "caution" | "safe" | "unverifiable"`.
- `summary` — 1–2 sentence plain-English explanation, ready for WhatsApp.
- `evidence` — list of source citations (so we can show our work).

## Design rules

1. **Parallel fetches with timeouts.** Use `asyncio.gather(..., return_exceptions=True)`
   with a hard 3 s wall-clock so a slow source can't hold up a reply.
2. **"Unverifiable" is a valid answer.** Never default to "safe" on missing
   data — silent false-negatives are worse than honest gaps.
3. **Pure scoring function.** The score formula lives in `engine.py` and takes
   plain data in, plain data out — no I/O. Easy to unit-test.

## Public API (intent)

```python
from services.matcher.engine import match

verdict = await match(
    barcode_payload="8901234567890",  # from a decoder OR typed by the user
    ocr_text="...",                   # may be None for the code-text path
    scrape_data={...},                # optional
)
```
