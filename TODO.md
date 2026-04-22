# TODO

Tracked deferrals from the image-to-verdict implementation pass. Items are
roughly ordered by user impact.

## Verification depth

- [ ] **Non-URL QR / EAN-13 lookup.** Today `services/matcher/engine.py` returns
      `unverifiable` when the barcode payload isn't a URL (no page to compare
      against). Plan: query a free barcode-lookup API (UPCitemdb,
      barcodelookup) for product info, then run the same matcher against that
      JSON. Stub belongs in `services/scraper/lookups/` or a new
      `services/lookup/` package.
- [ ] **CDSCO DAVA, OpenFDA, DrugBank, PubChem fetchers.** The original product
      spec (see [project.md](project.md)) wants authoritative source lookups
      alongside the manufacturer-page scrape. Add as parallel tasks inside
      `match()` behind feature flags so we can roll them in one source at a
      time.

## Scraper hardening

- [ ] **CapSolver integration.** Detection lives in
      [services/scraper/agent.py](services/scraper/agent.py) (the
      `_CAPTCHA_MARKERS` keyword check). Wire the actual solve + token
      injection when we hit a real CAPTCHA-gated portal.
- [ ] **Per-site Playwright strategies.** The generic `innerText` grab is
      enough for plain pages but loses structure on real manufacturer
      portals. Add `services/scraper/strategies/<host>.py` modules and a host
      -> strategy registry in `agent.py`.
- [ ] **Browser pool lifecycle hook.** `shutdown_browser()` exists but isn't
      called yet; wire it into `app.main.create_app` via
      `app.add_event_handler("shutdown", ...)` so we don't leak Chromium on
      reload / SIGTERM.

## Matcher / OCR follow-ups

- [ ] **Field extractor coverage.** Regexes in
      [services/matcher/engine.py](services/matcher/engine.py) cover the
      common label conventions; add tests + tune for at least 5 real Indian
      pharma packs we have on hand.
- [ ] **Confidence-aware verdict.** Today the score is purely the mean fuzzy
      ratio. Weight it by Tesseract / Gemini confidence so a low-quality OCR
      doesn't drag a true-match into "caution".
- [ ] **LLM summary.** Replace the static one-sentence `summary` in
      `_label_for(...)` with a short LLM-generated explanation once data
      shapes are stable (gated on `GOOGLE_API_KEY`).

## Out-of-scope features (intentional)

- [ ] **WhatsApp send/receive.** [services/whatsapp/](services/whatsapp/)
      stays a stub until a provider is picked (see
      [docs/whatsapp-research.md](docs/whatsapp-research.md)).
- [ ] **Frontend.** [frontend/](frontend/) is README-only; scaffold with
      `npx create-next-app` when an internal dashboard is needed.

## Infra

- [ ] **Caching.** Add Redis (or even an in-process LRU) keyed on the barcode
      payload — repeat lookups on the same pack should be sub-100ms.
- [ ] **Observability.** Wire structured logs and a simple request counter
      via `app/core/logging.py` once we deploy somewhere.
- [ ] **Dockerfile.** [infra/](infra/) is a placeholder; the image needs
      `libzbar0`, `tesseract-ocr`, and Playwright's Chromium pre-installed.
