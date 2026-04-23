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
import threading
from dataclasses import dataclass, field
from typing import Any

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


# ---------------------------------------------------------------------------
# Playwright singleton running in a dedicated thread.
#
# On Windows the default asyncio event loop (ProactorEventLoop used by
# uvicorn) cannot spawn subprocesses from coroutines, which makes
# ``async_playwright`` fail with ``NotImplementedError``.  We sidestep
# this entirely by running Playwright's **sync** API in a background
# daemon thread that owns its own (non-asyncio) context.  Every call
# from the async world is dispatched to that thread via a Future.
# ---------------------------------------------------------------------------
_pw_lock = threading.Lock()
_pw = None        # playwright sync context manager result
_browser = None   # sync Browser instance


def _ensure_browser():
    """Lazily start Playwright + Chromium inside the calling thread (sync)."""
    global _pw, _browser
    if _browser is not None:
        return _browser
    with _pw_lock:
        if _browser is None:
            from playwright.sync_api import sync_playwright
            _pw = sync_playwright().start()
            _browser = _pw.chromium.launch(headless=True)
    return _browser


def _sync_scrape(url: str, timeout_ms: int) -> dict:
    """Run the full scrape synchronously (meant to be called in a thread)."""
    browser = _ensure_browser()
    context = browser.new_context()
    page = context.new_page()
    try:
        response = page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        http_status = response.status if response else None
        title = page.title()
        visible_text: str = page.evaluate("() => document.body.innerText")
        html = page.content()
        return {
            "title": title,
            "visible_text": visible_text,
            "html": html,
            "http_status": http_status,
            "error": None,
        }
    except Exception as exc:
        return {"title": None, "visible_text": None, "html": None,
                "http_status": None, "error": exc}
    finally:
        context.close()


async def shutdown_browser() -> None:
    """Close the singleton on app shutdown so we don't leak Chromium processes.

    FastAPI's ``app.on_event("shutdown")`` is the natural caller — wire it in
    when the app gets a real lifecycle.
    """
    global _browser, _pw
    with _pw_lock:
        if _browser is not None:
            _browser.close()
            _browser = None
        if _pw is not None:
            _pw.stop()
            _pw = None


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
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None, _sync_scrape, url, int(timeout_s * 1000)
        )
    except ImportError:
        logger.warning("Playwright not installed; scraper unavailable.")
        return ScrapeResult(url=url, status="browser_unavailable")
    except Exception as exc:
        logger.exception("Failed to launch headless browser.")
        return ScrapeResult(url=url, status="browser_unavailable", error_detail=str(exc))

    if result["error"] is not None:
        return _classify_navigation_error(url, result["error"])

    # 4xx/5xx upstream — return what we have but tag the status so the
    # client can show "the manufacturer's site is down" instead of a
    # vague "couldn't compare".
    if result["http_status"] is not None and result["http_status"] >= 400:
        return ScrapeResult(
            url=url,
            fields={},
            raw_html=None,
            captcha_solved=False,
            status="http_error",
            http_status=result["http_status"],
            error_detail=f"Target returned HTTP {result['http_status']}",
        )

    title = result["title"] or ""
    visible_text = result["visible_text"] or ""
    html = result["html"] or ""

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
