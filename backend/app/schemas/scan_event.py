"""Pydantic schemas for MedicineScanEvent."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AuthenticityVerdictEnum


class ScanEventCreate(BaseModel):
    user_id: uuid.UUID | None = None
    medicine_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    barcode_data: str | None = Field(None, max_length=500)
    ocr_text: str | None = None
    authenticity_verdict: AuthenticityVerdictEnum
    verdict_score: float | None = Field(None, ge=0, le=10)
    verdict_details: dict[str, Any] | None = None
    country_code: str | None = Field(None, max_length=2)


class ScanEventRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    medicine_id: uuid.UUID | None
    batch_id: uuid.UUID | None
    scanned_at: datetime
    barcode_data: str | None
    authenticity_verdict: AuthenticityVerdictEnum
    verdict_score: float | None
    verdict_details: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScanEventSummary(BaseModel):
    """Lightweight projection for listing a user's scan history."""

    id: uuid.UUID
    scanned_at: datetime
    barcode_data: str | None
    authenticity_verdict: AuthenticityVerdictEnum
    medicine_brand_name: str | None = None
    medicine_generic_name: str | None = None

    model_config = ConfigDict(from_attributes=True)
