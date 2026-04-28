"""
lookup_product_db tool — pgvector semantic search + exact barcode lookup.

Used when the agent needs to find a product in TrustLens DB:
  - Check if a scanned medicine is in the DB
  - Find similar medicines by name (pgvector cosine similarity)
  - Fetch drug interaction info for a medicine

Returns a formatted text summary of matching products.
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def lookup_product_db(name: str, barcode: str | None = None) -> str:
    """
    Look up a medicine or grocery product in the TrustLens database.

    Use this when the user asks about a specific product and you want to:
    - Verify if a medicine is in the database
    - Find drug interactions for a medicine the user takes
    - Get official batch/expiry data for a medicine

    Args:
        name:    Product or medicine name (used for semantic search).
        barcode: Optional barcode string for exact lookup.

    Returns:
        Text description of matching products found, or a not-found message.
    """
    logger.info("tool.lookup_product_db | name=%r barcode=%r", name, barcode)

    try:
        from app.core.database import get_async_session_context
        from sqlalchemy import text

        async with get_async_session_context() as session:
            results: list[str] = []

            # ── 1. Exact barcode lookup (fast path) ─────────────────────────
            if barcode:
                row = await session.execute(
                    text("""
                        SELECT m.brand_name, m.generic_name, m.manufacturer_name,
                               mb.batch_number, mb.expiry_date
                        FROM medicines m
                        LEFT JOIN medicine_batches mb ON mb.medicine_id = m.id
                        WHERE m.barcode = :bc
                        LIMIT 1
                    """),
                    {"bc": barcode},
                )
                rec = row.fetchone()
                if rec:
                    results.append(
                        f"Exact match: {rec.brand_name} ({rec.generic_name}), "
                        f"Mfr: {rec.manufacturer_name}, "
                        f"Batch: {rec.batch_number or 'N/A'}, "
                        f"Expiry: {rec.expiry_date or 'N/A'}"
                    )
                    logger.info("tool.lookup_product_db | barcode hit brand=%r", rec.brand_name)

            # ── 2. pgvector semantic search ──────────────────────────────────
            if not results:
                # Embed the query name with OpenAI text-embedding-3-small
                from app.core.config import get_settings
                s = get_settings()
                if not s.openai_api_key:
                    logger.warning("tool.lookup_product_db | no OPENAI_API_KEY for embeddings")
                    return f"No database record found for '{name}' (embedding search unavailable)."

                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=s.openai_api_key, base_url=s.openai_base_url)
                emb_resp = await client.embeddings.create(
                    model=s.embedding_model,
                    input=name,
                )
                vec = emb_resp.data[0].embedding
                vec_str = "[" + ",".join(map(str, vec)) + "]"

                rows = await session.execute(
                    text("""
                        SELECT m.brand_name, m.generic_name, m.manufacturer_name,
                               1 - (m.name_embedding::vector <=> :vec::vector) AS similarity
                        FROM medicines m
                        WHERE m.name_embedding IS NOT NULL
                        ORDER BY m.name_embedding::vector <=> :vec::vector
                        LIMIT 3
                    """),
                    {"vec": vec_str},
                )
                recs = rows.fetchall()
                for r in recs:
                    if r.similarity >= 0.50:
                        results.append(
                            f"Match ({r.similarity:.0%}): {r.brand_name} ({r.generic_name}), "
                            f"Mfr: {r.manufacturer_name}"
                        )
                        logger.info(
                            "tool.lookup_product_db | semantic hit brand=%r score=%.2f",
                            r.brand_name, r.similarity,
                        )

            if results:
                return "Products found in TrustLens database:\n" + "\n".join(results)
            return f"No products matching '{name}' found in the database."

    except Exception as exc:
        logger.warning("tool.lookup_product_db | error: %s", exc)
        return f"Database lookup failed: {exc}"
