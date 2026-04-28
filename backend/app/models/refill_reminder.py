"""
RefillReminder — pre-computed medicine refill dates and notification tracking.

WHY pre-compute rather than compute on-demand:
  The reminder date is static once a prescription is filled. Pre-computing it
  means a background job only needs to do a simple ``reminder_date <= today``
  query — no runtime arithmetic, no re-parsing frequency strings.

COMPUTE LOGIC:
  days_supply  = ceil(quantity_prescribed / daily_doses(frequency))
  finish_date  = start_date + timedelta(days=days_supply)
  reminder_date = finish_date - timedelta(days=7)     # 7-day lead time

  daily_doses mapping (IntakeFrequencyEnum):
    once_daily       → 1
    twice_daily      → 2
    thrice_daily     → 3
    four_times_daily → 4
    weekly           → 0.143 (1/7)
    every_other_day  → 0.5
    as_needed / with_food / before_food / after_food → 1 (conservative estimate)
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base
from app.models.enums import IntakeFrequencyEnum


class RefillReminder(Base):
    __tablename__ = "refill_reminders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    medicine_id = Column(UUID(as_uuid=True), ForeignKey("medicines.id", ondelete="CASCADE"), nullable=False)

    # Optional link to the specific prescription item that triggered this reminder.
    prescription_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("prescription_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    start_date           = Column(Date, nullable=False)
    quantity_prescribed  = Column(Integer, nullable=False)                # e.g. 30 tablets
    frequency            = Column(Enum(IntakeFrequencyEnum), nullable=False)
    days_supply          = Column(Integer, nullable=False)                # computed
    finish_date          = Column(Date, nullable=False)                   # computed
    reminder_date        = Column(Date, nullable=False)                   # finish_date - 7 days

    # Notification state
    is_sent  = Column(Boolean, nullable=False, default=False)
    sent_at  = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        # Primary query pattern: "all unsent reminders due today or earlier"
        Index("ix_refill_reminders_due", "reminder_date", "is_sent"),
        Index("ix_refill_reminders_user",  "user_id"),
    )
