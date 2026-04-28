"""
UserHealthProfile — 1:1 extension of the User table.

WHY a separate table instead of columns on ``users``:
  Health data has different access-control and retention requirements than
  identity data. Separating them lets us apply row-level security in Supabase
  selectively, and makes the ``users`` table leaner for auth-only queries.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk
from app.models.enums import BloodGroupEnum, DietaryPreferenceEnum

if TYPE_CHECKING:
    from app.models.user import User


class UserHealthProfile(Base):
    __tablename__ = "user_health_profiles"

    id: Mapped[uuid_pk]
    # UNIQUE ensures the 1:1 constraint at the DB level — not just application logic.
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    dietary_preference: Mapped[DietaryPreferenceEnum | None] = mapped_column(
        sa.Enum(DietaryPreferenceEnum, name="dietary_preference_enum")
    )
    blood_group: Mapped[BloodGroupEnum | None] = mapped_column(
        sa.Enum(BloodGroupEnum, name="blood_group_enum")
    )
    # height / weight are stored for future BMI-aware nutritional advice,
    # not for medical diagnosis.
    height_cm: Mapped[float | None] = mapped_column(sa.Numeric(5, 1))
    weight_kg: Mapped[float | None] = mapped_column(sa.Numeric(5, 1))
    # Free-text notes the user adds about their health context
    # (e.g., "recovering from surgery", "pregnant").
    # Shown only to the user — never used as a medical claim.
    health_notes: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[created_at_col]
    updated_at: Mapped[updated_at_col]

    user: Mapped["User"] = relationship("User", back_populates="health_profile")

    def __repr__(self) -> str:
        return f"<UserHealthProfile user={self.user_id} diet={self.dietary_preference}>"
