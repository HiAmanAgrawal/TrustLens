from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import ProductTypeEnum, ReportTypeEnum


class CommunityReportCreate(BaseModel):
    product_id:   uuid.UUID
    product_type: ProductTypeEnum
    report_type:  ReportTypeEnum
    batch_id:     Optional[uuid.UUID] = None
    description:  Optional[str]       = Field(None, max_length=1000)


class CommunityReportResponse(BaseModel):
    id:                 uuid.UUID
    product_id:         uuid.UUID
    product_type:       ProductTypeEnum
    report_type:        ReportTypeEnum
    batch_id:           Optional[uuid.UUID]
    description:        Optional[str]
    is_auto_flagged:    bool
    flag_count_at_time: Optional[int]
    is_verified:        bool
    created_at:         datetime

    model_config = {"from_attributes": True}


class CommunityFlagStatus(BaseModel):
    product_id:    uuid.UUID
    product_type:  ProductTypeEnum
    batch_id:      Optional[uuid.UUID]
    report_count:  int
    is_flagged:    bool
    threshold:     int
