"""Raw barcode / QR code input endpoint.

A sibling of ``routes_images``. The user (or admin client) already has the
decoded string — typed off a pack, copied from an invoice, or read from a
website — and wants the same verdict without going through image decoding.

Keeping this on its own route, rather than overloading ``/images``, keeps each
endpoint's wire contract trivial: ``/images`` is multipart, ``/codes`` is JSON.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.schemas.verdict import VerdictResponse
from app.services.pipeline import verify_code

router = APIRouter()


class CodeSubmission(BaseModel):
    """User-submitted barcode / QR / batch string.

    ``symbology`` is optional — most callers don't know it, and the matcher
    can usually infer it from the payload format. We accept a hint anyway
    because a frontend that *does* know (e.g. it just scanned with a webcam)
    saves us the inference cost.
    """

    code: str = Field(..., min_length=4, max_length=512, description="The decoded code text")
    symbology: str | None = Field(
        default=None,
        description="Optional hint: 'QRCODE', 'EAN13', 'CODE128', 'DATAMATRIX', ...",
    )


@router.post("", response_model=VerdictResponse)
async def submit_code(payload: CodeSubmission) -> VerdictResponse:
    """Verify an already-decoded barcode / QR string.

    Same downstream pipeline as ``/images``, minus the barcode + OCR steps.
    """
    return await verify_code(payload.code.strip())
