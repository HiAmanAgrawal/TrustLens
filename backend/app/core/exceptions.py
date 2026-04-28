"""
Application-level exception hierarchy for TrustLens.

WHY a custom hierarchy instead of bare HTTPException:
  - Service layer raises domain errors (``MedicineNotFound``) without knowing
    HTTP — that keeps services reusable in non-HTTP contexts (CLI, tests, agents).
  - The global exception handler in main.py maps each domain error to the
    correct HTTP status code and ``ErrorResponse`` envelope in one place,
    rather than scattering ``status_code`` decisions across every route.

USAGE:
    # In a service:
    raise MedicineNotFound(medicine_id=str(id))

    # In main.py exception handler:
    @app.exception_handler(TrustLensError)
    async def _domain_error_handler(request, exc):
        return JSONResponse(status_code=exc.http_status, content=...)
"""

from __future__ import annotations


class TrustLensError(Exception):
    """Base class for all application-level errors.

    ``http_status``   — HTTP status code the global handler will use.
    ``user_message``  — Short, human-readable text safe to show the end user.
                        Must NOT leak internal details.
    ``detail``        — Optional developer-facing detail (logged, not returned).
    """

    http_status: int = 500
    user_message: str = "An unexpected error occurred."

    def __init__(self, user_message: str | None = None, *, detail: str | None = None) -> None:
        self.user_message = user_message or self.__class__.user_message
        self.detail = detail
        super().__init__(self.user_message)


# ---------------------------------------------------------------------------
# 400 Bad Request
# ---------------------------------------------------------------------------

class InvalidInputError(TrustLensError):
    http_status = 400
    user_message = "Invalid input provided."


class BarcodeDecodeError(InvalidInputError):
    user_message = "Could not decode a barcode or QR code from the image."


class UnsupportedFileTypeError(InvalidInputError):
    user_message = "File type is not supported. Please upload a JPEG or PNG image."


# ---------------------------------------------------------------------------
# 401 / 403
# ---------------------------------------------------------------------------

class AuthenticationError(TrustLensError):
    http_status = 401
    user_message = "Authentication is required."


class PermissionDeniedError(TrustLensError):
    http_status = 403
    user_message = "You do not have permission to perform this action."


# ---------------------------------------------------------------------------
# 404 Not Found
# ---------------------------------------------------------------------------

class NotFoundError(TrustLensError):
    http_status = 404
    user_message = "Resource not found."


class UserNotFoundError(NotFoundError):
    def __init__(self, user_id: str) -> None:
        super().__init__(f"User '{user_id}' not found.", detail=f"user_id={user_id}")


class MedicineNotFoundError(NotFoundError):
    def __init__(self, medicine_id: str) -> None:
        super().__init__(
            f"Medicine '{medicine_id}' not found.",
            detail=f"medicine_id={medicine_id}",
        )


class BatchNotFoundError(NotFoundError):
    def __init__(self, batch_id: str) -> None:
        super().__init__(
            f"Medicine batch '{batch_id}' not found.",
            detail=f"batch_id={batch_id}",
        )


class GroceryItemNotFoundError(NotFoundError):
    def __init__(self, item_id: str) -> None:
        super().__init__(
            f"Grocery item '{item_id}' not found.",
            detail=f"item_id={item_id}",
        )


class PrescriptionNotFoundError(NotFoundError):
    def __init__(self, prescription_id: str) -> None:
        super().__init__(
            f"Prescription '{prescription_id}' not found.",
            detail=f"prescription_id={prescription_id}",
        )


# ---------------------------------------------------------------------------
# 409 Conflict
# ---------------------------------------------------------------------------

class ConflictError(TrustLensError):
    http_status = 409
    user_message = "A conflict occurred with the current state of the resource."


class DuplicateUserError(ConflictError):
    user_message = "A user with this phone number or email already exists."


class DuplicateBarcodeError(ConflictError):
    user_message = "A product with this barcode already exists."


# ---------------------------------------------------------------------------
# 422 Unprocessable
# ---------------------------------------------------------------------------

class UnprocessableError(TrustLensError):
    http_status = 422
    user_message = "The request was well-formed but could not be processed."


# ---------------------------------------------------------------------------
# 503 Upstream failures
# ---------------------------------------------------------------------------

class ExternalServiceError(TrustLensError):
    http_status = 503
    user_message = "An external service is temporarily unavailable. Please try again."


class ScraperError(ExternalServiceError):
    user_message = "Could not retrieve data from the manufacturer's website."


class SearchServiceError(ExternalServiceError):
    user_message = "Web search is temporarily unavailable."
