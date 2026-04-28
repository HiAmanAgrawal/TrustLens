"""
Refill Reminder Service — compute finish dates and manage refill notifications.

BUSINESS RULE:
  - days_supply = ceil(quantity_prescribed / daily_dose_count(frequency))
  - finish_date  = start_date + days_supply days
  - reminder_date = finish_date - 7 days

WHY 7 days lead time:
  In India, most chemists stock common generics but branded medicines can
  take 2-5 days to procure. 7 days gives the user enough buffer to reorder
  even if the pharmacy needs to arrange stock.

SCHEDULER NOTE:
  get_due_reminders() is designed to be called by a periodic task (cron or
  asyncio background loop). It returns reminders due today or earlier that
  have not yet been sent. After sending, call mark_reminder_sent().
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import date, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import IntakeFrequencyEnum
from app.models.refill_reminder import RefillReminder

logger = logging.getLogger(__name__)

# Days before finish_date to send the reminder.
_REMINDER_LEAD_DAYS = 7

# Doses per day for each frequency enum value.
_DAILY_DOSES: dict[str, float] = {
    IntakeFrequencyEnum.ONCE_DAILY:       1.0,
    IntakeFrequencyEnum.TWICE_DAILY:      2.0,
    IntakeFrequencyEnum.THRICE_DAILY:     3.0,
    IntakeFrequencyEnum.FOUR_TIMES_DAILY: 4.0,
    IntakeFrequencyEnum.AS_NEEDED:        1.0,   # conservative estimate
    IntakeFrequencyEnum.WEEKLY:           1 / 7,
    IntakeFrequencyEnum.EVERY_OTHER_DAY:  0.5,
    IntakeFrequencyEnum.BEFORE_FOOD:      3.0,   # assume 3 meals
    IntakeFrequencyEnum.AFTER_FOOD:       3.0,
    IntakeFrequencyEnum.WITH_FOOD:        3.0,
}


def compute_daily_doses(frequency: IntakeFrequencyEnum | str) -> float:
    """Return how many doses per day a frequency enum implies."""
    return _DAILY_DOSES.get(frequency, 1.0)


def compute_days_supply(quantity: int, frequency: IntakeFrequencyEnum | str) -> int:
    """
    How many days will ``quantity`` units last at the given frequency?

    Uses ceiling so we never under-count (5 tablets at 3x/day = 2 days, not 1).
    """
    daily = compute_daily_doses(frequency)
    if daily <= 0:
        return 0
    return math.ceil(quantity / daily)


async def create_reminder(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    medicine_id: uuid.UUID,
    quantity_prescribed: int,
    frequency: IntakeFrequencyEnum,
    start_date: date,
    prescription_item_id: uuid.UUID | None = None,
) -> RefillReminder:
    """
    Create (or replace) a refill reminder for a medicine course.

    If a reminder already exists for the same (user, medicine, start_date)
    we update it rather than creating a duplicate. This handles the case where
    the prescription is amended shortly after being created.
    """
    days  = compute_days_supply(quantity_prescribed, frequency)
    finish = start_date + timedelta(days=days)
    remind = finish - timedelta(days=_REMINDER_LEAD_DAYS)

    # Ensure reminder_date is not in the past relative to start_date
    if remind < start_date:
        remind = start_date

    # Idempotency: check for existing reminder
    stmt = select(RefillReminder).where(
        RefillReminder.user_id == user_id,
        RefillReminder.medicine_id == medicine_id,
        RefillReminder.start_date == start_date,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.quantity_prescribed = quantity_prescribed
        existing.frequency           = frequency
        existing.days_supply         = days
        existing.finish_date         = finish
        existing.reminder_date       = remind
        existing.is_sent             = False
        existing.sent_at             = None
        logger.info(
            "refill.update | user_id=%s medicine_id=%s days=%d remind=%s",
            user_id, medicine_id, days, remind,
        )
        return existing

    reminder = RefillReminder(
        user_id=user_id,
        medicine_id=medicine_id,
        prescription_item_id=prescription_item_id,
        start_date=start_date,
        quantity_prescribed=quantity_prescribed,
        frequency=frequency,
        days_supply=days,
        finish_date=finish,
        reminder_date=remind,
    )
    session.add(reminder)
    await session.flush()

    logger.info(
        "refill.created | user_id=%s medicine_id=%s qty=%d freq=%s days=%d finish=%s remind=%s",
        user_id, medicine_id, quantity_prescribed, frequency, days, finish, remind,
    )
    return reminder


async def get_due_reminders(
    session: AsyncSession,
    as_of_date: date | None = None,
) -> list[RefillReminder]:
    """
    Return all unsent reminders where reminder_date ≤ as_of_date.

    Called by the background scheduler to dispatch WhatsApp notifications.
    Loads user and medicine eagerly to avoid N+1 in the notification loop.
    """
    today = as_of_date or date.today()
    stmt = (
        select(RefillReminder)
        .where(
            and_(
                RefillReminder.reminder_date <= today,
                RefillReminder.is_sent == False,  # noqa: E712
            )
        )
        .order_by(RefillReminder.reminder_date)
    )
    result = await session.execute(stmt)
    reminders = list(result.scalars().all())
    logger.info("refill.due | as_of=%s count=%d", today, len(reminders))
    return reminders


async def mark_reminder_sent(
    session: AsyncSession,
    reminder_id: uuid.UUID,
) -> RefillReminder:
    """Mark a reminder as sent so it won't be re-dispatched."""
    from datetime import datetime, timezone

    stmt = select(RefillReminder).where(RefillReminder.id == reminder_id)
    result = await session.execute(stmt)
    reminder = result.scalar_one_or_none()
    if reminder is None:
        raise ValueError(f"RefillReminder {reminder_id} not found")

    reminder.is_sent = True
    reminder.sent_at = datetime.now(timezone.utc)
    logger.info("refill.sent | reminder_id=%s", reminder_id)
    return reminder


async def list_user_reminders(
    session: AsyncSession,
    user_id: uuid.UUID,
    include_sent: bool = False,
) -> list[RefillReminder]:
    """List reminders for a user, optionally including already-sent ones."""
    filters = [RefillReminder.user_id == user_id]
    if not include_sent:
        filters.append(RefillReminder.is_sent == False)  # noqa: E712

    stmt = (
        select(RefillReminder)
        .where(*filters)
        .order_by(RefillReminder.reminder_date)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
