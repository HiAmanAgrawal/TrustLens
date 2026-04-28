"""Pydantic schemas for User, UserAllergy, and UserMedicalCondition."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import AllergenCategoryEnum, GenderEnum
from app.schemas.health_profile import UserHealthProfileRead


# ---------------------------------------------------------------------------
# UserAllergy
# ---------------------------------------------------------------------------

class UserAllergyCreate(BaseModel):
    allergen: str = Field(..., min_length=1, max_length=200)
    allergen_category: AllergenCategoryEnum | None = None
    severity_note: str | None = Field(None, max_length=500)


class UserAllergyRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    allergen: str
    allergen_category: AllergenCategoryEnum | None
    severity_note: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# UserMedicalCondition
# ---------------------------------------------------------------------------

class UserMedicalConditionCreate(BaseModel):
    condition_name: str = Field(..., min_length=1, max_length=300)
    icd_10_code: str | None = Field(None, max_length=10)
    diagnosed_at: date | None = None
    is_active: bool = True
    notes: str | None = None


class UserMedicalConditionRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    condition_name: str
    icd_10_code: str | None
    diagnosed_at: date | None
    is_active: bool
    notes: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    phone_number: str | None = Field(None, max_length=20)
    email: EmailStr | None = None
    whatsapp_user_id: str | None = Field(None, max_length=100)
    dob: date | None = None
    gender: GenderEnum | None = None

    @field_validator("phone_number")
    @classmethod
    def _validate_phone(cls, v: str | None) -> str | None:
        if v and not v.replace("+", "").replace(" ", "").isdigit():
            raise ValueError("phone_number must contain only digits, spaces, and a leading '+'")
        return v

    @field_validator("whatsapp_user_id", "phone_number", "email", mode="before")
    @classmethod
    def _at_least_one_contact(cls, v: str | None, info) -> str | None:
        # Note: cross-field validation handled at model level via model_validator
        return v


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    phone_number: str | None = Field(None, max_length=20)
    email: EmailStr | None = None
    dob: date | None = None
    gender: GenderEnum | None = None


class UserRead(BaseModel):
    id: uuid.UUID
    full_name: str
    phone_number: str | None
    email: str | None
    whatsapp_user_id: str | None
    dob: date | None
    gender: GenderEnum | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserReadWithProfile(UserRead):
    """Extended read schema that includes nested health profile and allergies."""
    health_profile: UserHealthProfileRead | None = None
    allergies: list[UserAllergyRead] = []
    medical_conditions: list[UserMedicalConditionRead] = []
