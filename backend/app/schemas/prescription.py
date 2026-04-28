"""Pydantic schemas for Prescription and PrescriptionItem."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import IntakeFrequencyEnum
from app.schemas.medicine import MedicineRead


class PrescriptionItemCreate(BaseModel):
    medicine_id: uuid.UUID
    dosage_instructions: str = Field(..., min_length=1)
    intake_frequency: IntakeFrequencyEnum
    duration_days: int | None = Field(None, gt=0)
    quantity_prescribed: int | None = Field(None, gt=0)
    notes: str | None = None


class PrescriptionItemRead(BaseModel):
    id: uuid.UUID
    prescription_id: uuid.UUID
    medicine_id: uuid.UUID
    dosage_instructions: str
    intake_frequency: IntakeFrequencyEnum
    duration_days: int | None
    quantity_prescribed: int | None
    notes: str | None
    medicine: MedicineRead | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrescriptionCreate(BaseModel):
    doctor_name: str | None = Field(None, max_length=300)
    doctor_registration_no: str | None = Field(None, max_length=100)
    hospital_name: str | None = Field(None, max_length=300)
    issued_date: date
    valid_until: date | None = None
    notes: str | None = None
    items: list[PrescriptionItemCreate] = []


class PrescriptionUpdate(BaseModel):
    doctor_name: str | None = None
    hospital_name: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class PrescriptionRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    doctor_name: str | None
    doctor_registration_no: str | None
    hospital_name: str | None
    issued_date: date
    valid_until: date | None
    notes: str | None
    is_active: bool
    items: list[PrescriptionItemRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
