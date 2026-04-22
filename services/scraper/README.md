# services/scraper/

A headless-browser scraping agent. Used to pull data from manufacturer QR
portals and other sources that don't expose a clean API.

## Why a real browser

Many Indian pharma portals are JavaScript-heavy, gate behind CAPTCHAs, or
serve content only after a token-bearing XHR fires. `requests` + BeautifulSoup
is not enough — we need Playwright with a real Chromium instance.

## Layout

```text
scraper/
├── agent.py        # Public API: scrape_url(url, options) -> dict
└── strategies/     # One file per site / CAPTCHA flavour
```

## CAPTCHA bypass

We delegate solving to **CapSolver** (or any 2Captcha-compatible service) and
inject the token back into the page via Playwright. The agent should:

1. Detect the CAPTCHA type (reCAPTCHA v2/v3, hCaptcha, Cloudflare Turnstile).
2. Submit the site key + page URL to the solver.
3. Patch the resolved token into the DOM (`document.getElementById('g-recaptcha-response').innerText = token`).
4. Submit the form normally.

The CapSolver API key lives in `CAPSOLVER_API_KEY`. Never log it.

## Background execution

Scrapes can take 5–30 s and must not block a webhook reply. The FastAPI route
should:

- Send an interim "verifying…" message via `services/whatsapp`.
- Schedule the scrape as a background task (FastAPI `BackgroundTasks` short-term,
  Arq / APScheduler long-term).
- When the result is ready, fire a follow-up WhatsApp message.

## Public API (intent)

```python
from services.scraper.agent import scrape_url

data = await scrape_url("https://example.com/verify?batch=ABC123")
```
