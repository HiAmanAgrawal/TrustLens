# services/ocr/

Extract text from an image — labels, batch numbers, ingredient lists.

## Strategy

Two-tier, cheapest first:

1. **Tesseract (`pytesseract`)** — free, runs locally, fine for clean printed
   text. Use this for the bulk of label OCR.
2. **LLM vision fallback** (Claude Vision / GPT-4o Vision) — used when
   Tesseract returns low-confidence text, or when the page contains complex
   layouts (curved labels, low light, mixed scripts).

The fallback decision lives inside `extract_text` so callers don't need to
care which engine ran.

## Public API (intent)

```python
from services.ocr.extractor import extract_text

text = await extract_text(image_bytes)
```

## Notes

- Pre-process images with PIL: greyscale + adaptive threshold dramatically
  improves Tesseract accuracy on phone photos.
- Strip EXIF before sending bytes to a third-party LLM (privacy: location).
