"""Pydantic schemas for UserHealthProfile."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BloodGroupEnum, DietaryPreferenceEnum


class UserHealthProfileCreate(BaseModel):
    dietary_preference: DietaryPreferenceEnum | None = None
    blood_group: BloodGroupEnum | None = None
    height_cm: float | None = Field(None, gt=0, le=300)
    weight_kg: float | None = Field(None, gt=0, le=500)
    health_notes: str | None = None


class UserHealthProfileUpdate(UserHealthProfileCreate):
    pass


class UserHealthProfileRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    dietary_preference: DietaryPreferenceEnum | None
    blood_group: BloodGroupEnum | None
    height_cm: float | None
    weight_kg: float | None
    health_notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
