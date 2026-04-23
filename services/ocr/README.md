# services/ocr/

Extract text from an image — labels, batch numbers, ingredient lists,
nutrition tables, FSSAI / manufacturing licence numbers.

## Strategy

Two-tier, **cloud-primary**:

1. **Google Gemini Vision** (`google-genai`) — primary engine when
   `GOOGLE_API_KEY` is set. Handles curved labels, glare, mixed scripts,
   hand-stamped dates, dense nutrition tables, and small print on Indian
   pharma / grocery packs that Tesseract chokes on. Same chain runs for
   medicines and grocery items.
2. **Tesseract (`pytesseract`)** — local fallback. Used whenever Gemini
   is unavailable: missing API key, auth failure, rate limit, network
   error, timeout, or empty response. Free, fully offline.

The chain decision lives inside `extract_text` so callers don't need to
care which engine ran. The returned `OcrResult.engine` says which engine
ultimately produced the text; `OcrResult.status` says how the chain
unfolded so the API layer can surface a precise note to the client (e.g.
"Gemini key was rejected — used local OCR instead").

## Public API

```python
from services.ocr.extractor import extract_text

result = await extract_text(image_bytes)
print(result.text, result.engine, result.status, result.confidence)
```

## Status semantics

| `status`                  | Meaning                                                                                         |
| ------------------------- | ----------------------------------------------------------------------------------------------- |
| `ok`                      | Primary (Gemini) returned strong text. Happy path.                                              |
| `fallback_used`           | Gemini was unavailable / returned thin text; local Tesseract handled it. Informational.         |
| `fallback_auth_failed`    | Gemini rejected the API key. Tesseract may have produced text — surfaced anyway as actionable.  |
| `fallback_rate_limited`   | Gemini hit a 429. Tesseract may have produced text. Retry later for cloud quality.              |
| `fallback_failed`         | Other Gemini error / timeout / empty response, and Tesseract also didn't help.                  |
| `fallback_unavailable`    | No `GOOGLE_API_KEY` configured **and** Tesseract not installed. Worst case for the deployment.  |
| `low_confidence`          | Best result we could produce was weak (Tesseract path).                                         |
| `no_text`                 | Neither engine produced any text.                                                               |
| `tesseract_missing`       | Local fallback unavailable (only emitted when the cloud also failed).                           |
| `image_unreadable`        | PIL couldn't open the bytes.                                                                    |

## Notes

- Gemini call is wrapped in a 25-second wall-clock timeout so a hung
  API doesn't pin the request.
- Tesseract input goes through PIL preprocessing (greyscale,
  autocontrast, sharpen). Gemini does NOT — it works better on the raw
  bytes.
- MIME-type detection matters for HEIC photos (iPhone). The chain
  inspects PIL's `Image.format` and passes the right `Content-Type` to
  Gemini.
- The Gemini prompt is in `_GEMINI_PROMPT` and is intentionally compact
  but directive: long checklisty prompts cause vision models to skip
  fields. Tweak it carefully and re-run the regression fixtures.
