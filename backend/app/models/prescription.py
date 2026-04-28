"""
Prescription and PrescriptionItem models.

prescriptions ──< prescription_items >── medicines

WHY store prescriptions:
  - The agent needs to know which medicines the user is currently taking to
    check for drug-drug interactions at scan time.
  - The UI can display a "medicine cabinet" view for caregiver use cases.

SCOPE GUARDRAIL: We store prescription data for the user's own reference.
  We do NOT validate dosage safety, replace a doctor's advice, or share
  prescription data with any third party.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk
from app.models.enums import IntakeFrequencyEnum

if TYPE_CHECKING:
    from app.models.medicine import Medicine
    from app.models.user import User


class Prescription(Base):
    __tablename__ = "prescriptions"

    id: Mapped[uuid_pk]
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doctor_name: Mapped[str | None] = mapped_column(sa.String(300))
    # IMC (Indian Medical Council) registration number
    doctor_registration_no: Mapped[str | None] = mapped_column(sa.String(100))
    hospital_name: Mapped[str | None] = mapped_column(sa.String(300))
    issued_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(sa.Date)
    notes: Mapped[str | None] = mapped_column(sa.Text)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    created_at: Mapped[created_at_col]
    updated_at: Mapped[updated_at_col]

    user: Mapped["User"] = relationship("User", back_populates="prescriptions")
    items: Mapped[list["PrescriptionItem"]] = relationship(
        "PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan"
    )

    __table_args__ = (sa.Index("ix_prescriptions_user_id", "user_id"),)

    def __repr__(self) -> str:
        return f"<Prescription id={self.id} user={self.user_id} issued={self.issued_date}>"


class PrescriptionItem(Base):
    """
    One medicine line on a prescription.

    dosage_instructions is free text to faithfully capture the doctor's note
    (e.g., "1 tablet twice daily after food for 7 days") rather than trying
    to normalise into structured fields that may not map cleanly.
    """

    __tablename__ = "prescription_items"

    id: Mapped[uuid_pk]
    prescription_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("prescriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    medicine_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("medicines.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    dosage_instructions: Mapped[str] = mapped_column(sa.Text, nullable=False)
    intake_frequency: Mapped[IntakeFrequencyEnum] = mapped_column(
        sa.Enum(IntakeFrequencyEnum, name="intake_frequency_enum"), nullable=False
    )
    duration_days: Mapped[int | None] = mapped_column(sa.Integer)
    quantity_prescribed: Mapped[int | None] = mapped_column(sa.Integer)
    notes: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[created_at_col]

    prescription: Mapped["Prescription"] = relationship("Prescription", back_populates="items")
    medicine: Mapped["Medicine"] = relationship("Medicine", back_populates="prescription_items")

    __table_args__ = (
        sa.Index("ix_prescription_items_prescription_id", "prescription_id"),
        sa.Index("ix_prescription_items_medicine_id", "medicine_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<PrescriptionItem prescription={self.prescription_id} "
            f"medicine={self.medicine_id} freq={self.intake_frequency}>"
        )
