"""
FastAPI application factory — Phase 2 (database-backed, i18n, v1 API).

Startup sequence:
  1. Configure structured logging.
  2. Load i18n catalogues.
  3. Ensure pgvector extension exists.
  4. Mount all routers (legacy /images, /codes, /webhook + new /v1).

The factory pattern ensures no I/O happens at import time so tests can build
a fresh app without connecting to a real database.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Legacy routes (pre-Phase-1 pipeline — kept intact for backwards compatibility)
from app.api import routes_codes, routes_health, routes_images, routes_whatsapp
# New v1 API router
from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.exceptions import TrustLensError
from app.core.i18n import load_catalogues
from app.core.logging import configure_logging
from app.schemas.status import MESSAGES, ErrorResponse, StatusCode

logger = logging.getLogger(__name__)

_HTTP_TO_STATUS_CODE: dict[int, StatusCode] = {
    400: StatusCode.INVALID_REQUEST,
    401: StatusCode.UNAUTHORIZED,
    403: StatusCode.FORBIDDEN,
    404: StatusCode.NOT_FOUND,
    405: StatusCode.METHOD_NOT_ALLOWED,
    413: StatusCode.PAYLOAD_TOO_LARGE,
    415: StatusCode.UNSUPPORTED_MEDIA_TYPE,
    422: StatusCode.INVALID_REQUEST,
    429: StatusCode.RATE_LIMITED,
}


def _error_payload(code: StatusCode, *, detail: str | None = None) -> dict:
    return ErrorResponse(status=code, message=MESSAGES[code], detail=detail).model_dump(mode="json")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """
    Manage resource lifecycle: startup → yield → shutdown.

    Using the lifespan context manager (FastAPI 0.93+) instead of
    on_event("startup") / on_event("shutdown") because the new API composes
    better with pytest-asyncio and avoids deprecation warnings.
    """
    settings = get_settings()
    logger.info("app.startup | env=%s version=%s", settings.app_env, settings.app_version)

    # 1. Static i18n catalogues loaded into memory once
    load_catalogues(settings.supported_languages)
    logger.info("app.i18n.loaded | languages=%s", settings.supported_languages)

    # 2. AI i18n cache sized from settings (in-process LRU for translated strings)
    from app.core.i18n_ai import configure_cache
    configure_cache(settings.i18n_cache_size)
    logger.info(
        "app.i18n_ai.configured | provider=%s enabled=%s cache_size=%d",
        settings.i18n_ai_provider,
        settings.use_ai_i18n,
        settings.i18n_cache_size,
    )

    # 2. pgvector column patching (must run before any schema introspection)
    from app.db import apply_pgvector_columns
    apply_pgvector_columns()

    # 3. Ensure pgvector extension in the DB (idempotent, fast SELECT)
    try:
        from app.core.database import get_session_factory
        from app.core.database import ensure_pgvector_extension
        factory = get_session_factory()
        async with factory() as session:
            await ensure_pgvector_extension(session)
    except Exception as exc:
        # Non-fatal at startup — the app can still serve non-vector routes
        logger.warning("app.startup.pgvector_extension_check_failed | error=%s", exc)

    logger.info("app.startup.complete")
    yield

    # --- Shutdown ---
    logger.info("app.shutdown.starting")
    from services.whatsapp.send_receive import close as wa_close
    await wa_close()

    from services.scraper.agent import shutdown_browser
    await shutdown_browser()

    from app.core.database import close_engine
    await close_engine()

    from app.services.session_service import close_redis
    await close_redis()

    logger.info("app.shutdown.complete")


def create_app() -> FastAPI:
    """Build and return the fully configured FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="TrustLens API",
        version=settings.app_version,
        docs_url="/docs",
        redoc_url=None,
        lifespan=_lifespan,
    )

    # ------------------------------------------------------------------ #
    # Exception handlers — every error shape goes through these handlers  #
    # ------------------------------------------------------------------ #

    @app.exception_handler(TrustLensError)
    async def _domain_error_handler(request: Request, exc: TrustLensError) -> JSONResponse:
        """
        Domain errors raised in service layer → HTTP response with correct status.

        The service layer knows nothing about HTTP; this handler bridges the gap
        so service code stays clean and routes stay thin.
        """
        logger.warning(
            "domain_error | type=%s msg=%r detail=%r",
            type(exc).__name__, exc.user_message, exc.detail,
        )
        status_code = exc.http_status
        code = _HTTP_TO_STATUS_CODE.get(status_code, StatusCode.INTERNAL_ERROR)
        return JSONResponse(
            status_code=status_code,
            content=_error_payload(code, detail=exc.user_message),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc.detail, StatusCode):
            code = exc.detail
            detail = None
        else:
            code = _HTTP_TO_STATUS_CODE.get(exc.status_code, StatusCode.INTERNAL_ERROR)
            detail = exc.detail if isinstance(exc.detail, str) else None
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(code, detail=detail),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else None
        detail = (
            f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}" if first else None
        )
        return JSONResponse(
            status_code=422,
            content=_error_payload(StatusCode.INVALID_REQUEST, detail=detail),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception | path=%s", request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_error_payload(StatusCode.INTERNAL_ERROR),
        )

    # ------------------------------------------------------------------ #
    # Routers                                                              #
    # ------------------------------------------------------------------ #

    # Legacy routes (pre-Phase-1 pipeline — unchanged)
    app.include_router(routes_health.router, tags=["health"])
    app.include_router(routes_images.router, prefix="/images", tags=["images"])
    app.include_router(routes_codes.router,  prefix="/codes",  tags=["codes"])
    app.include_router(routes_whatsapp.router, prefix="/webhook/whatsapp", tags=["whatsapp"])

    # New versioned API
    app.include_router(v1_router)

    # Developer testing portal — disabled in production
    if settings.app_env != "production":
        from app.api import testing as testing_module
        app.include_router(
            testing_module.router,
            prefix="/testing",
            tags=["testing-portal"],
        )
        logger.info("app.testing_portal.mounted | env=%s", settings.app_env)

    logger.info("app.routes_mounted")
    return app


# Module-level instance for ``uvicorn app.main:app``
app = create_app()
