# services/

Framework-agnostic Python packages. Anything in here can be imported by:

- the FastAPI app (`backend/app/...`)
- a CLI entry point
- a background worker
- a notebook / one-off script

…without dragging HTTP / FastAPI concerns along.

## Packages

| Package    | Responsibility                                                                 |
| ---------- | ------------------------------------------------------------------------------ |
| `whatsapp` | Send and receive WhatsApp messages. Provider chosen at runtime via an adapter. |
| `scraper`  | Headless Chromium (Playwright) scraping with CAPTCHA bypass.                   |
| `ocr`      | Extract text from an image (Tesseract first, LLM-vision fallback).             |
| `barcode`  | Decode barcodes / QR / DataMatrix into a structured payload.                   |
| `matcher`  | Combine extracted signals with external data sources to produce a verdict.     |

## Rules

1. **No `from fastapi import …` anywhere under `services/`.** That is a one-way coupling we never want.
2. **Public surface is small.** Each package exposes a few functions or a single class — internal helpers stay private.
3. **Async by default.** Most calls are I/O bound; sync wrappers can be added later if needed.
4. **Inputs and outputs are dataclasses or TypedDicts**, not raw dicts — callers should not have to guess the shape.
