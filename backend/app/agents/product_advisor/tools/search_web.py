"""
search_web tool — Tavily API web search for product advisor.

Used when the agent needs current information not in the product context:
  - Ingredient safety data not in the DB
  - Recent news about a product or brand
  - Dietary guidelines for a condition
  - E-code safety information

WHY async + to_thread:
  Tavily Python SDK is synchronous. asyncio.to_thread() prevents blocking the
  event loop while waiting for the HTTP response.
"""

from __future__ import annotations

import asyncio
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def search_web(query: str) -> str:
    """
    Search the web for current health, nutrition, or product safety information.

    Use this when you need:
    - Information about a specific ingredient or additive (e.g. 'E211 sodium benzoate safety')
    - Dietary guidelines (e.g. 'sugar intake limit for diabetics per day India')
    - Product-specific news or recall information
    - FSSAI regulations or standards

    Args:
        query: A specific, targeted search query.

    Returns:
        A text summary of the top search results.
    """
    logger.info("tool.search_web | query=%r", query[:100])

    try:
        from app.core.config import get_settings
        s = get_settings()

        if not s.tavily_api_key:
            logger.warning("tool.search_web | no TAVILY_API_KEY")
            return "Web search is unavailable (no Tavily API key configured)."

        from tavily import TavilyClient

        def _search() -> str:
            client = TavilyClient(api_key=s.tavily_api_key)
            results = client.search(
                query=query,
                max_results=min(s.tavily_max_results, 4),
                search_depth="basic",
                include_answer=True,
            )

            # Use Tavily's AI answer if available
            if results.get("answer"):
                logger.info("tool.search_web | got tavily answer len=%d", len(results["answer"]))
                return results["answer"]

            # Fallback: stitch together result snippets
            snippets = [
                f"[{r.get('title','')}]: {r.get('content','')}"
                for r in results.get("results", [])[:4]
                if r.get("content")
            ]
            combined = "\n\n".join(snippets)
            logger.info("tool.search_web | snippets=%d combined_len=%d", len(snippets), len(combined))
            return combined or "No relevant results found."

        return await asyncio.to_thread(_search)

    except Exception as exc:
        logger.warning("tool.search_web | error: %s", exc)
        return f"Web search failed: {exc}"
