"""Image upload endpoint — the *photo* input path.

Used by the admin dashboard / B2B clients to push an image and get back a
verdict. The WhatsApp webhook (when implemented) will reuse the same
``app.services.pipeline.verify_image`` glue so the behaviour stays identical
across transports.

For the *typed code* input path, see ``routes_codes`` — that one skips the
barcode + OCR steps.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.status import StatusCode
from app.schemas.verdict import VerdictResponse
from app.services.pipeline import verify_image

router = APIRouter()

# Reject anything bigger than 10 MB. A typical phone JPEG is < 5 MB; the cap
# protects the server from accidental DoS via huge uploads.
_MAX_BYTES = 10 * 1024 * 1024

# Image MIME types we know our pipeline handles. The browser/WhatsApp client
# almost always sets one of these correctly; rejecting anything else early
# saves us from feeding random bytes to PIL.
_ALLOWED_MIMES = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic", "image/heif"}
)


@router.post("", response_model=VerdictResponse)
async def upload_image(file: UploadFile = File(...)) -> VerdictResponse:
    """Accept an image, run barcode + OCR + scrape + matcher, return a verdict."""
    if file.content_type and file.content_type.lower() not in _ALLOWED_MIMES:
        # 415 is the right code here: the request was structurally fine, the
        # *body type* is wrong. Pass the StatusCode so the global handler
        # picks the canonical message.
        raise HTTPException(status_code=415, detail=StatusCode.UNSUPPORTED_MEDIA_TYPE)

    payload = await _read_capped(file)
    return await verify_image(payload)


async def _read_capped(file: UploadFile) -> bytes:
    """Read the upload while enforcing the size cap.

    We stream rather than calling ``file.read()`` outright because some clients
    can send multi-GB bodies and we'd rather refuse early than buffer them.
    """
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(64 * 1024):
        size += len(chunk)
        if size > _MAX_BYTES:
            raise HTTPException(status_code=413, detail=StatusCode.PAYLOAD_TOO_LARGE)
        chunks.append(chunk)
    if not chunks:
        raise HTTPException(status_code=400, detail=StatusCode.EMPTY_UPLOAD)
    return b"".join(chunks)
