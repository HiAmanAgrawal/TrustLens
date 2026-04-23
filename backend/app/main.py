"""FastAPI app factory.

The factory pattern keeps import-time work to a minimum and lets tests build a
fresh app instance with overridden settings. Production servers (uvicorn /
gunicorn) load ``app`` — the module-level instance built from default settings.

Exception handlers are registered here so every error response — whether
raised by a route, by FastAPI's validation layer, or by an unhandled
exception — comes back as the same ``ErrorResponse`` envelope. Clients can
then branch on ``status`` regardless of the HTTP code.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import routes_codes, routes_health, routes_images, routes_whatsapp
from app.core.config import get_settings
from app.schemas.status import MESSAGES, ErrorResponse, StatusCode

logger = logging.getLogger(__name__)


# Map common HTTP statuses to our ``StatusCode`` enum so handlers don't have
# to know the canonical mapping in N places.
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
    """Build a JSON-serialisable error envelope from a status code."""
    return ErrorResponse(status=code, message=MESSAGES[code], detail=detail).model_dump(
        mode="json"
    )


def create_app() -> FastAPI:
    """Build and return a configured FastAPI instance.

    Anything that touches I/O (DB pools, HTTP clients, queues) should attach
    here as startup hooks rather than at module import time.
    """
    settings = get_settings()

    app = FastAPI(
        title="TrustLens API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,  # one docs UI is enough
    )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Wrap HTTPExceptions in the unified ``ErrorResponse`` envelope.

        We register against ``StarletteHTTPException`` (the parent class)
        rather than FastAPI's subclass so this also catches the framework's
        own 404 / 405 responses for unknown routes.

        Routes can either raise ``HTTPException(status_code=413, detail=StatusCode.PAYLOAD_TOO_LARGE)``
        or pass any string in ``detail``; we figure out the canonical status
        code from the HTTP status, and use ``detail`` as supplementary info.
        """
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
    async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        """Pydantic / FastAPI validation errors → 422 with a friendly envelope."""
        # First validation error is usually the most actionable for the user.
        first = exc.errors()[0] if exc.errors() else None
        detail = (
            f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}"
            if first
            else None
        )
        return JSONResponse(
            status_code=422,
            content=_error_payload(StatusCode.INVALID_REQUEST, detail=detail),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
        """Last-resort handler — never leak a stack trace to the client."""
        logger.exception("Unhandled exception in request handler.", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_error_payload(StatusCode.INTERNAL_ERROR),
        )

    # Routers are mounted explicitly so the wiring is visible in one place.
    app.include_router(routes_health.router, tags=["health"])
    app.include_router(routes_images.router, prefix="/images", tags=["images"])
    app.include_router(routes_codes.router, prefix="/codes", tags=["codes"])
    app.include_router(routes_whatsapp.router, prefix="/webhook/whatsapp", tags=["whatsapp"])

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        """Release adapter resources (HTTP clients, browser instances)."""
        from services.whatsapp.send_receive import close as wa_close

        await wa_close()

    _ = settings  # silence unused-warning until settings are actually consumed

    return app


# Module-level instance for `uvicorn app.main:app`.
app = create_app()
