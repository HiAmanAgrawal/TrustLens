"""Headless-browser scraping agent.

Uses Playwright (Chromium) under the hood. Site-specific selectors live in
``strategies/`` so this module stays small and stable. For now we only ship a
generic strategy: load the page, return its title and visible text. That's
enough for a first-cut comparison against label OCR.

CAPTCHA bypass via CapSolver is wired as a TODO — the keyword detection is
already here, so plugging the solver in later is a small change.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover — imports only used for type hints
    from playwright.async_api import Browser

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScrapeResult:
    """Structured scrape output. Keep this stable — downstream matcher code
    depends on the field names.

    ``status`` is a free-form string (``"ok"``, ``"timeout"``, ``"dns_failed"``,
    ``"http_error"``, ``"captcha_blocked"``, ``"browser_unavailable"``,
    ``"failed"``) that the pipeline maps to a ``StatusCode``. We keep the
    HTTP-schema-free contract here so this module stays reusable outside the
    FastAPI app.
    """

    url: str
    fields: dict[str, Any] = field(default_factory=dict)   # extracted key/value pairs
    raw_html: str | None = None                            # kept for debugging only
    captcha_solved: bool = False
    status: str = "ok"
    http_status: int | None = None  # populated on http_error
    error_detail: str | None = None  # short message for debugging / logging


# Module-level browser singleton. Launching Chromium costs ~1–2 s; reusing the
# same instance across requests is the single biggest perf win we can make.
_browser: "Browser | None" = None
_browser_lock = asyncio.Lock()
_playwright_ctx = None  # opaque: holds the async_playwright() handle for shutdown


async def _get_browser() -> "Browser":
    """Lazily launch (and reuse) a Chromium instance.

    The lock prevents two concurrent first-callers from racing to launch two
    browsers and leaking one. Playwright is imported here (not at module top)
    so the rest of the codebase still loads when Playwright isn't installed.
    """
    global _browser, _playwright_ctx

    if _browser is not None:
        return _browser

    from playwright.async_api import async_playwright

    async with _browser_lock:
        if _browser is None:  # double-check inside the lock
            _playwright_ctx = await async_playwright().start()
            _browser = await _playwright_ctx.chromium.launch(headless=True)
    return _browser


async def shutdown_browser() -> None:
    """Close the singleton on app shutdown so we don't leak Chromium processes.

    FastAPI's ``app.on_event("shutdown")`` is the natural caller — wire it in
    when the app gets a real lifecycle.
    """
    global _browser, _playwright_ctx
    if _browser is not None:
        await _browser.close()
        _browser = None
    if _playwright_ctx is not None:
        await _playwright_ctx.stop()
        _playwright_ctx = None


# Substrings that hint a CAPTCHA stands between us and the page content.
# Used to set ``captcha_solved=False`` honestly so the matcher can downgrade
# its confidence rather than trusting an interstitial.
_CAPTCHA_MARKERS = ("g-recaptcha", "h-captcha", "cf-turnstile", "captcha")


async def scrape_url(url: str, *, timeout_s: float = 30.0) -> ScrapeResult:
    """Open ``url`` in headless Chromium and return the extracted fields.

    Generic-strategy flow:
      1. Get/launch the singleton browser.
      2. Open a fresh context (clean cookies per call — manufacturer portals
         sometimes leak previous-batch state).
      3. ``goto`` with ``networkidle`` so SPAs have a chance to render.
      4. Pull title + visible body text (``innerText``, not ``textContent``,
         to drop hidden elements and inline scripts).
      5. Heuristically flag CAPTCHA pages so the matcher can react.

    Always returns a ``ScrapeResult`` — even on failure — with ``status``
    set so the caller can surface a specific error to the user.
    """
    try:
        browser = await _get_browser()
    except ImportError:
        logger.warning("Playwright not installed; scraper unavailable.")
        return ScrapeResult(url=url, status="browser_unavailable")
    except Exception as exc:
        logger.exception("Failed to launch headless browser.")
        return ScrapeResult(url=url, status="browser_unavailable", error_detail=str(exc))

    context = await browser.new_context()
    page = await context.new_page()
    try:
        try:
            response = await page.goto(
                url, wait_until="networkidle", timeout=int(timeout_s * 1000)
            )
        except Exception as exc:
            return _classify_navigation_error(url, exc)

        # 4xx/5xx upstream — return what we have but tag the status so the
        # client can show "the manufacturer's site is down" instead of a
        # vague "couldn't compare".
        if response is not None and response.status >= 400:
            return ScrapeResult(
                url=url,
                fields={},
                raw_html=None,
                captcha_solved=False,
                status="http_error",
                http_status=response.status,
                error_detail=f"Target returned HTTP {response.status}",
            )

        title = await page.title()
        # ``innerText`` already collapses whitespace and skips ``display:none``
        # blocks — much cleaner than parsing raw HTML.
        visible_text: str = await page.evaluate("() => document.body.innerText")
        html = await page.content()

        captcha_present = any(marker in html.lower() for marker in _CAPTCHA_MARKERS)
        if captcha_present:
            # TODO: route to CapSolver, inject the token, re-submit, then
            # re-evaluate visible_text. For now we surface the page contents
            # but flag the status so the matcher / UI can react.
            logger.warning("CAPTCHA marker detected on %s; returning unverified page text.", url)
            return ScrapeResult(
                url=url,
                fields={"title": title, "visible_text": visible_text},
                raw_html=html,
                captcha_solved=False,
                status="captcha_blocked",
            )

        return ScrapeResult(
            url=url,
            fields={"title": title, "visible_text": visible_text},
            raw_html=html,
            captcha_solved=False,
            status="ok",
        )
    finally:
        # Always tear the context down — leaking contexts eventually exhausts
        # the browser's worker pool.
        await context.close()


def _classify_navigation_error(url: str, exc: BaseException) -> ScrapeResult:
    """Map a Playwright navigation exception to one of our ``status`` values."""
    msg = str(exc).lower()
    if "timeout" in msg or "exceeded" in msg:
        status = "timeout"
    elif any(k in msg for k in ("name_not_resolved", "dns", "address_unreachable")):
        status = "dns_failed"
    else:
        status = "failed"
    logger.warning("Scrape of %s failed (%s): %s", url, status, exc)
    return ScrapeResult(url=url, status=status, error_detail=str(exc)[:200])
