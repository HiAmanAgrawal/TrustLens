"""
Tavily web search client — structured wrapper used in TWO fallback scenarios.

  1. Medicine verification: when Playwright can't reach the manufacturer
     verification portal (timeout / CAPTCHA / DNS failure), Tavily searches
     for batch and manufacturer details so the matcher still has something
     to work with.

  2. FSSAI verification: when the Playwright FoSCoS scrape fails, Tavily
     searches "FSSAI license {number}" to surface the registered business
     name and status from the public web.

All calls are fire-and-forget from the pipeline's perspective — failures
degrade to an empty result ({"status": "fallback_unavailable"}) rather than
raising, because the scan result must never be blocked by a search engine.

Rate-limiting strategy:
  Tavily free tier = 1 000 searches/month (~33/day). We stay within that by:
    - Only calling Tavily when the primary (Playwright) path fails.
    - Capping results at 3 per call (fewer tokens, faster, cheaper).
    - Running queries only once per unique key (no polling).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TavilyResult:
    """Structured result from a single Tavily search call.

    ``status`` mirrors the scraper's convention so pipeline code can branch
    uniformly: "ok", "no_results", "unavailable", "api_key_missing".
    """

    status: str                                  # ok | no_results | unavailable | api_key_missing
    query: str = ""
    snippets: list[str] = field(default_factory=list)   # top-N result snippets
    raw_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def combined_text(self) -> str:
        """Merge all snippets into one blob — fed directly to the matcher."""
        return "\n\n".join(self.snippets)


async def search_medicine_info(
    *,
    product_name: str,
    batch_no: str | None = None,
    manufacturer: str | None = None,
    max_results: int = 3,
) -> TavilyResult:
    """Search for medicine batch/manufacturer data.

    Used as the Playwright scraper's fallback. The query is intentionally
    narrow so Tavily doesn't waste quota on irrelevant results.
    """
    parts = [product_name]
    if batch_no:
        parts.append(f"batch {batch_no}")
    if manufacturer:
        parts.append(manufacturer)
    parts.append("medicine verification India")

    query = " ".join(parts)
    logger.info("tavily.search_medicine | query=%r", query[:80])
    return await _search(query, max_results=max_results)


async def search_fssai_license(
    license_number: str,
    *,
    max_results: int = 3,
) -> TavilyResult:
    """Verify an FSSAI license number via Tavily web search.

    The query targets the public FSSAI/FoSCoS portal results which appear
    in search indexes so recent licenses are findable even if the FoSCoS
    portal itself is slow or blocked.
    """
    query = f"FSSAI license {license_number} food safety India FoSCoS"
    logger.info("tavily.search_fssai | license=%s", license_number)
    return await _search(query, max_results=max_results)


async def search_grocery_product(
    *,
    product_name: str,
    fssai_no: str | None = None,
    max_results: int = 3,
) -> TavilyResult:
    """General grocery product lookup — used when no FSSAI number is found."""
    parts = [product_name, "India food product safety"]
    if fssai_no:
        parts.append(f"FSSAI {fssai_no}")
    query = " ".join(parts)
    logger.info("tavily.search_grocery | query=%r", query[:80])
    return await _search(query, max_results=max_results)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _search(query: str, *, max_results: int = 3) -> TavilyResult:
    """Execute the Tavily search and convert to TavilyResult."""
    from app.core.config import get_settings
    settings = get_settings()

    if not settings.tavily_api_key:
        logger.warning("tavily._search | TAVILY_API_KEY not configured; search skipped")
        return TavilyResult(status="api_key_missing", query=query)

    try:
        # tavily-python is synchronous; run in a thread so we don't block
        # the FastAPI event loop. asyncio.to_thread is Python 3.9+.
        import asyncio
        from tavily import TavilyClient  # type: ignore[import]

        client = TavilyClient(api_key=settings.tavily_api_key)
        effective_max = min(max_results, settings.tavily_max_results)

        raw = await asyncio.to_thread(
            client.search,
            query,
            max_results=effective_max,
            search_depth="basic",       # "basic" uses fewer credits than "advanced"
        )

        results: list[dict[str, Any]] = raw.get("results", [])
        if not results:
            logger.info("tavily._search | no_results query=%r", query[:60])
            return TavilyResult(status="no_results", query=query, raw_results=[])

        snippets = [
            r.get("content") or r.get("snippet") or ""
            for r in results
            if r.get("content") or r.get("snippet")
        ]
        logger.info(
            "tavily._search | ok results=%d snippets=%d",
            len(results), len(snippets),
        )
        return TavilyResult(
            status="ok",
            query=query,
            snippets=snippets,
            raw_results=results,
        )

    except Exception as exc:
        logger.warning("tavily._search | failed query=%r error=%s", query[:60], exc)
        return TavilyResult(status="unavailable", query=query, error=str(exc))
