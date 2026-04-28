from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import IntakeFrequencyEnum


class RefillReminderCreate(BaseModel):
    medicine_id:          uuid.UUID
    quantity_prescribed:  int        = Field(..., gt=0)
    frequency:            IntakeFrequencyEnum
    start_date:           date
    prescription_item_id: Optional[uuid.UUID] = None


class RefillReminderResponse(BaseModel):
    id:                  uuid.UUID
    user_id:             uuid.UUID
    medicine_id:         uuid.UUID
    prescription_item_id: Optional[uuid.UUID]
    start_date:          date
    quantity_prescribed: int
    frequency:           IntakeFrequencyEnum
    days_supply:         int
    finish_date:         date
    reminder_date:       date
    is_sent:             bool
    sent_at:             Optional[datetime]
    created_at:          datetime

    model_config = {"from_attributes": True}


class RefillReminderList(BaseModel):
    reminders:   list[RefillReminderResponse]
    total:       int
    include_sent: bool
