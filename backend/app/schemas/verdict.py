"""Wire-level shape of the verdict response.

Mirrors ``services.matcher.engine.Verdict`` but with explicit Pydantic types
so OpenAPI / Swagger stays useful and clients have something to codegen
against. We intentionally surface the raw extracted text + per-side fields —
they make the verdict explainable in the UI without an extra round-trip.

Every response also carries a top-level ``status`` (machine-readable) and
``message`` (human-readable), plus an ordered list of ``notes`` describing
everything the pipeline wants the client to know. See ``status.py`` for the
catalogue.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.status import Note, StatusCode


class BarcodeInfo(BaseModel):
    payload: str
    symbology: str
    rotation: int = 0
    status: Literal["decoded", "detected_undecoded"] = "decoded"


class OcrInfo(BaseModel):
    engine: str = Field(..., description='"tesseract" or "gemini"')
    confidence: float = Field(..., ge=0.0, le=1.0)
    text: str


class PageInfo(BaseModel):
    url: str
    title: str | None = None
    text: str | None = None
    captcha_detected: bool = False


class VerdictResponse(BaseModel):
    status: StatusCode = Field(
        ...,
        description=(
            "Top-level machine-readable status. Branch on this in the UI; "
            "see app/schemas/status.py for the full catalogue."
        ),
    )
    message: str = Field(
        ...,
        description="One-sentence human-readable summary suitable for direct display.",
    )
    notes: list[Note] = Field(
        default_factory=list,
        description=(
            "Ordered list of everything the pipeline wants the client to know — "
            "stage failures, fallbacks used, data-quality warnings."
        ),
    )

    verdict: Literal["high_risk", "caution", "safe", "unverifiable"]
    score: int = Field(..., ge=0, le=10)
    summary: str = Field(
        ...,
        description=(
            "Verdict-specific summary from the matcher. Distinct from "
            "``message`` so clients can show both ('what happened' + 'what we found')."
        ),
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Per-field comparison strings; empty when no fields overlapped.",
    )
    barcode: BarcodeInfo | None = None
    ocr: OcrInfo | None = None
    page: PageInfo | None = None
    label_fields: dict[str, str] = Field(default_factory=dict)
    page_fields: dict[str, str] = Field(default_factory=dict)
