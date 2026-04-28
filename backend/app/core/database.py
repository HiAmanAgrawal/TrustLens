"""
Async SQLAlchemy engine and session factory.

WHY async:
  FastAPI routes are async-first. Using a sync SQLAlchemy session in an async
  route blocks the entire event loop for the duration of every DB query —
  unacceptable at scale. AsyncSession delegates I/O to asyncpg which uses
  PostgreSQL's wire protocol without thread-pool overhead.

USAGE (in a FastAPI dependency):
    from app.core.database import get_async_session

    @router.get("/medicines/{id}")
    async def get_medicine(
        id: UUID,
        session: AsyncSession = Depends(get_async_session),
    ):
        result = await session.get(Medicine, id)

The engine is created lazily on first call to ``get_engine()`` so that test
suites can override ``Settings.database_url`` before the engine is initialised.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Module-level singletons; initialised lazily via get_engine() / get_session_factory().
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """
    Return (and lazily create) the singleton async engine.

    Pool settings are tuned for a typical containerised API pod:
      pool_size      — baseline connections kept alive
      max_overflow   — extra connections allowed under burst load
      pool_timeout   — how long to wait for a free connection before raising
      pool_pre_ping  — send a cheap SELECT 1 before returning a stale connection
                       from the pool (important in long-idle Supabase deployments)
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        logger.info(
            "database.engine.creating | url=%s pool_size=%d",
            _redact_dsn(settings.database_url),
            settings.db_pool_size,
        )
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_pre_ping=True,
            echo=settings.log_level == "DEBUG",  # log SQL only in DEBUG mode
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return (and lazily create) the singleton session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,  # prevents lazy-load errors after commit
            autoflush=False,         # flush explicitly so we control when SQL fires
        )
    return _session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a per-request database session.

    The session is committed on clean exit and rolled back on exception,
    then always closed. This ensures every request starts with a clean
    transaction and connection pool leaks cannot accumulate.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            logger.debug("database.session.opened")
            yield session
            await session.commit()
            logger.debug("database.session.committed")
        except Exception:
            logger.warning("database.session.rollback", exc_info=True)
            await session.rollback()
            raise
        finally:
            logger.debug("database.session.closed")


async def close_engine() -> None:
    """
    Dispose the engine pool — call on app shutdown.

    FastAPI's ``lifespan`` context manager is the intended caller so that
    Chromium and DB connections are both released before the process exits.
    """
    global _engine, _session_factory
    if _engine is not None:
        logger.info("database.engine.disposing")
        await _engine.dispose()
        _engine = None
        _session_factory = None


# ---------------------------------------------------------------------------
# Supabase / pgvector bootstrap helpers
# ---------------------------------------------------------------------------

async def ensure_pgvector_extension(session: AsyncSession) -> None:
    """
    Create the pgvector extension if it doesn't already exist.

    WHY: Supabase enables pgvector by default, but a bare PostgreSQL instance
    (local dev, CI) needs the extension created explicitly. Running this on
    startup is idempotent and fast.
    """
    logger.info("database.pgvector.ensuring_extension")
    await session.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    await session.commit()
    logger.info("database.pgvector.extension_ready")


def _redact_dsn(dsn: str) -> str:
    """Remove credentials from a DSN before logging it."""
    try:
        url = sa.engine.make_url(dsn)
        return url.render_as_string(hide_password=True)
    except Exception:
        return "<dsn redacted>"
