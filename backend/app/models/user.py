"""
User identity and normalized health-profile satellite tables.

Schema decisions:
  - Allergies and medical conditions are in separate tables (not arrays) so
    that we can index, query, and JOIN on them without array operators — e.g.
    "find all users allergic to peanuts" is a simple WHERE, not GIN-array.
  - whatsapp_user_id is kept on the user table (not the profile) because it
    drives authentication for the zero-install WhatsApp flow.
  - dob/gender are nullable — we never block onboarding on demographics.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk
from app.models.enums import AllergenCategoryEnum, GenderEnum

if TYPE_CHECKING:
    from app.models.health_profile import UserHealthProfile
    from app.models.medicine import UserDrugReaction
    from app.models.prescription import Prescription
    from app.models.scan_event import MedicineScanEvent


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid_pk]
    full_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    phone_number: Mapped[str | None] = mapped_column(sa.String(20), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(sa.String(255), unique=True, index=True)
    # WhatsApp sender ID (e.g. "whatsapp:+919876543210") used to route inbound
    # messages to the correct user without requiring app login.
    whatsapp_user_id: Mapped[str | None] = mapped_column(sa.String(100), unique=True, index=True)
    dob: Mapped[date | None] = mapped_column(sa.Date)
    gender: Mapped[GenderEnum | None] = mapped_column(sa.Enum(GenderEnum, name="gender_enum"))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True, server_default=sa.true())
    created_at: Mapped[created_at_col]
    updated_at: Mapped[updated_at_col]

    # ---- relationships ----
    health_profile: Mapped["UserHealthProfile | None"] = relationship(
        "UserHealthProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    allergies: Mapped[list["UserAllergy"]] = relationship(
        "UserAllergy", back_populates="user", cascade="all, delete-orphan"
    )
    medical_conditions: Mapped[list["UserMedicalCondition"]] = relationship(
        "UserMedicalCondition", back_populates="user", cascade="all, delete-orphan"
    )
    scan_events: Mapped[list["MedicineScanEvent"]] = relationship(
        "MedicineScanEvent", back_populates="user"
    )
    prescriptions: Mapped[list["Prescription"]] = relationship(
        "Prescription", back_populates="user", cascade="all, delete-orphan"
    )
    drug_reactions: Mapped[list["UserDrugReaction"]] = relationship(
        "UserDrugReaction", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        sa.CheckConstraint(
            "phone_number IS NOT NULL OR email IS NOT NULL OR whatsapp_user_id IS NOT NULL",
            name="ck_users_at_least_one_contact",
        ),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} name={self.full_name!r}>"


class UserAllergy(Base):
    """
    Normalized allergen records — one row per allergen per user.

    WHY separate table:
      The agent needs to check "does this product contain any of the user's
      allergens?" at query time. Storing as an array requires unnesting;
      a JOIN on this table is faster and index-friendly.
    """

    __tablename__ = "user_allergies"

    id: Mapped[uuid_pk]
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Free-text allergen name as the user stated it ("shrimp", "tree nuts", etc.)
    allergen: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    # Classified category for structured checks — may be null if auto-classification failed
    allergen_category: Mapped[AllergenCategoryEnum | None] = mapped_column(
        sa.Enum(AllergenCategoryEnum, name="allergen_category_enum")
    )
    severity_note: Mapped[str | None] = mapped_column(sa.String(500))
    created_at: Mapped[created_at_col]

    user: Mapped["User"] = relationship("User", back_populates="allergies")

    __table_args__ = (
        sa.UniqueConstraint("user_id", "allergen", name="uq_user_allergies_user_allergen"),
        sa.Index("ix_user_allergies_user_id", "user_id"),
        sa.Index("ix_user_allergies_category", "allergen_category"),
    )

    def __repr__(self) -> str:
        return f"<UserAllergy user={self.user_id} allergen={self.allergen!r}>"


class UserMedicalCondition(Base):
    """
    One row per medical condition per user.

    WHY ICD-10:
      Normalizing to ICD-10 codes enables future drug-contraindication checks
      (e.g., NSAID + renal failure) without string-matching condition names
      across different languages.
    """

    __tablename__ = "user_medical_conditions"

    id: Mapped[uuid_pk]
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    condition_name: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    # ICD-10 code — optional but enables structured interaction checks
    icd_10_code: Mapped[str | None] = mapped_column(sa.String(10))
    diagnosed_at: Mapped[date | None] = mapped_column(sa.Date)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    notes: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[created_at_col]

    user: Mapped["User"] = relationship("User", back_populates="medical_conditions")

    __table_args__ = (
        sa.Index("ix_user_conditions_user_id", "user_id"),
        sa.Index("ix_user_conditions_icd10", "icd_10_code"),
    )

    def __repr__(self) -> str:
        return f"<UserMedicalCondition user={self.user_id} condition={self.condition_name!r}>"
