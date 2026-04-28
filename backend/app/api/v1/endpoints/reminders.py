"""
Refill Reminder API.

Endpoints:
  POST /v1/users/{user_id}/reminders           — create/update a refill reminder
  GET  /v1/users/{user_id}/reminders           — list active reminders
  GET  /v1/users/{user_id}/reminders/all       — list including sent
  POST /v1/reminders/{reminder_id}/mark-sent   — mark reminder as sent (scheduler use)
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession
from app.schemas.refill_reminder import (
    RefillReminderCreate,
    RefillReminderList,
    RefillReminderResponse,
)
from app.services.refill_service import (
    create_reminder,
    list_user_reminders,
    mark_reminder_sent,
)

router = APIRouter()


@router.post("/{user_id}/reminders", response_model=RefillReminderResponse, status_code=201)
async def create_refill_reminder(
    user_id: uuid.UUID,
    body:    RefillReminderCreate,
    db:      DBSession,
):
    """
    Create (or update if it already exists) a refill reminder for a medicine course.

    finish_date and reminder_date are computed automatically from
    quantity_prescribed, frequency, and start_date.
    """
    reminder = await create_reminder(
        db,
        user_id=user_id,
        medicine_id=body.medicine_id,
        quantity_prescribed=body.quantity_prescribed,
        frequency=body.frequency,
        start_date=body.start_date,
        prescription_item_id=body.prescription_item_id,
    )
    await db.commit()
    return reminder


@router.get("/{user_id}/reminders", response_model=RefillReminderList)
async def list_active_reminders(
    user_id:      uuid.UUID,
    db:           DBSession,
    include_sent: bool = Query(False),
):
    """List refill reminders for a user. Excludes already-sent reminders by default."""
    reminders = await list_user_reminders(db, user_id, include_sent=include_sent)
    return RefillReminderList(
        reminders=reminders,
        total=len(reminders),
        include_sent=include_sent,
    )


@router.post("/reminders/{reminder_id}/mark-sent", response_model=RefillReminderResponse)
async def mark_sent(
    reminder_id: uuid.UUID,
    db:          DBSession,
):
    """
    Mark a reminder as sent. Called by the background scheduler after
    dispatching the WhatsApp notification.
    """
    reminder = await mark_reminder_sent(db, reminder_id)
    await db.commit()
    return reminder
