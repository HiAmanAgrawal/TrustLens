"""Pydantic schemas for Salt, Medicine, MedicineBatch, DrugInteraction, UserDrugReaction."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    DosageFormEnum,
    InteractionSeverityEnum,
    ReactionSeverityEnum,
)


# ---------------------------------------------------------------------------
# Salt
# ---------------------------------------------------------------------------

class SaltCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    iupac_name: str | None = Field(None, max_length=500)
    cas_number: str | None = Field(None, max_length=20)
    molecular_formula: str | None = Field(None, max_length=100)
    molecular_weight_g_mol: float | None = Field(None, gt=0)


class SaltRead(BaseModel):
    id: uuid.UUID
    name: str
    iupac_name: str | None
    cas_number: str | None
    molecular_formula: str | None
    molecular_weight_g_mol: float | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Medicine
# ---------------------------------------------------------------------------

class MedicineSaltEntry(BaseModel):
    """Salt entry embedded inside a medicine create/read payload."""
    salt_id: uuid.UUID
    quantity_mg: float | None = Field(None, gt=0)


class MedicineCreate(BaseModel):
    generic_name: str = Field(..., min_length=1, max_length=300)
    brand_name: str = Field(..., min_length=1, max_length=300)
    dosage_form: DosageFormEnum
    strength: str = Field(..., min_length=1, max_length=100)
    manufacturer: str = Field(..., min_length=1, max_length=300)
    cdsco_license: str | None = Field(None, max_length=100)
    barcode: str | None = Field(None, max_length=100)
    salts: list[MedicineSaltEntry] = []


class MedicineUpdate(BaseModel):
    generic_name: str | None = Field(None, min_length=1, max_length=300)
    brand_name: str | None = Field(None, min_length=1, max_length=300)
    dosage_form: DosageFormEnum | None = None
    strength: str | None = Field(None, min_length=1, max_length=100)
    manufacturer: str | None = Field(None, min_length=1, max_length=300)
    cdsco_license: str | None = None
    barcode: str | None = None
    is_active: bool | None = None


class MedicineRead(BaseModel):
    id: uuid.UUID
    generic_name: str
    brand_name: str
    dosage_form: DosageFormEnum
    strength: str
    manufacturer: str
    cdsco_license: str | None
    barcode: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MedicineReadWithSalts(MedicineRead):
    salts: list[SaltRead] = []


# ---------------------------------------------------------------------------
# MedicineBatch
# ---------------------------------------------------------------------------

class MedicineBatchCreate(BaseModel):
    medicine_id: uuid.UUID
    batch_no: str = Field(..., min_length=1, max_length=100)
    manufacturing_date: date | None = None
    expiry_date: date
    barcode: str | None = Field(None, max_length=200)


class MedicineBatchRead(BaseModel):
    id: uuid.UUID
    medicine_id: uuid.UUID
    batch_no: str
    manufacturing_date: date | None
    expiry_date: date
    is_verified: bool
    barcode: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Drug Interaction
# ---------------------------------------------------------------------------

class DrugInteractionCreate(BaseModel):
    salt_id_a: uuid.UUID
    salt_id_b: uuid.UUID
    severity: InteractionSeverityEnum
    description: str
    mechanism: str | None = None
    clinical_significance: str | None = None
    source: str | None = Field(None, max_length=100)


class DrugInteractionRead(BaseModel):
    id: uuid.UUID
    salt_id_a: uuid.UUID
    salt_id_b: uuid.UUID
    severity: InteractionSeverityEnum
    description: str
    mechanism: str | None
    clinical_significance: str | None
    source: str | None
    salt_a: SaltRead | None = None
    salt_b: SaltRead | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# UserDrugReaction
# ---------------------------------------------------------------------------

class UserDrugReactionCreate(BaseModel):
    salt_id: uuid.UUID
    reaction_description: str = Field(..., min_length=1)
    severity: ReactionSeverityEnum


class UserDrugReactionRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    salt_id: uuid.UUID
    reaction_description: str
    severity: ReactionSeverityEnum
    reported_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
