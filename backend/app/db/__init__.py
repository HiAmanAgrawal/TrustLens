"""
Database package.

Exposes the pgvector column override helper so ``alembic/env.py`` can call
``apply_pgvector_columns()`` after all models are imported.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

logger = logging.getLogger(__name__)


def apply_pgvector_columns() -> None:
    """
    Replace the placeholder Text columns with actual pgvector Vector columns.

    WHY deferred replacement:
      The ``pgvector`` package is optional (e.g. a developer running only the
      WhatsApp pipeline without Supabase doesn't need it). By keeping the column
      definition as ``sa.Text`` in the model file and patching it here at
      migration/startup time, the models remain importable even without pgvector
      installed.

    Call this once during ``alembic/env.py`` and once in the FastAPI lifespan
    BEFORE ``Base.metadata.create_all()``.
    """
    try:
        from pgvector.sqlalchemy import Vector  # type: ignore[import]
    except ImportError:
        logger.warning(
            "pgvector package not installed — Vector columns will remain as Text. "
            "Run `pip install pgvector` for semantic search support."
        )
        return

    from app.db.base import Base

    vector_tables = {
        "medicines": "name_embedding",
        "grocery_items": "name_embedding",
    }

    for table_name, col_name in vector_tables.items():
        if table_name not in Base.metadata.tables:
            logger.warning("apply_pgvector_columns: table %r not found — skipped", table_name)
            continue

        table = Base.metadata.tables[table_name]
        col = table.c.get(col_name)
        if col is None:
            continue

        # Patch the column type in-place on the Table object.
        # SQLAlchemy does not provide a public API for this, but replacing the
        # ``type`` attribute directly works reliably because the type is only
        # used at DDL generation time (Alembic) and query-bind time (SQLAlchemy).
        col.type = Vector(1536)
        logger.info("pgvector: patched %s.%s → Vector(1536)", table_name, col_name)
