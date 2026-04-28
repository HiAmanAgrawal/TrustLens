"""
Community Reports API — crowd-sourced product safety flags.

Endpoints:
  POST   /v1/reports                      — submit a report (anonymous or authenticated)
  GET    /v1/reports/{product_type}/{id}  — list reports for a product
  GET    /v1/reports/{product_type}/{id}/status — flag status + count
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession
from app.models.enums import ProductTypeEnum
from app.schemas.community_report import (
    CommunityFlagStatus,
    CommunityReportCreate,
    CommunityReportResponse,
)
from app.services import community_report_service

router = APIRouter()


@router.post("", response_model=CommunityReportResponse, status_code=201)
async def submit_report(
    body: CommunityReportCreate,
    db: DBSession,
    # user_id would come from auth middleware in a real deployment;
    # for now, accept optional header / future JWT claim.
    user_id: Optional[uuid.UUID] = Query(None, description="Authenticated user ID (optional)"),
):
    """Submit a community report for a product or batch."""
    report = await community_report_service.create_report(
        db,
        product_id=body.product_id,
        product_type=body.product_type,
        report_type=body.report_type,
        user_id=user_id,
        batch_id=body.batch_id,
        description=body.description,
    )
    await db.commit()
    return report


@router.get("/{product_type}/{product_id}", response_model=list[CommunityReportResponse])
async def list_reports(
    product_type: ProductTypeEnum,
    product_id:   uuid.UUID,
    db:           DBSession,
    batch_id:     Optional[uuid.UUID] = Query(None),
    limit:        int                 = Query(50, ge=1, le=200),
):
    """List community reports for a product, optionally filtered by batch."""
    return await community_report_service.get_reports(
        db,
        product_id=product_id,
        product_type=product_type,
        batch_id=batch_id,
        limit=limit,
    )


@router.get("/{product_type}/{product_id}/status", response_model=CommunityFlagStatus)
async def flag_status(
    product_type: ProductTypeEnum,
    product_id:   uuid.UUID,
    db:           DBSession,
    batch_id:     Optional[uuid.UUID] = Query(None),
):
    """Return report count and auto-flag status for a product/batch."""
    count = await community_report_service.get_report_count(
        db, product_id=product_id, product_type=product_type, batch_id=batch_id,
    )
    flagged = await community_report_service.is_community_flagged(
        db, product_id=product_id, product_type=product_type, batch_id=batch_id,
    )
    return CommunityFlagStatus(
        product_id=product_id,
        product_type=product_type,
        batch_id=batch_id,
        report_count=count,
        is_flagged=flagged,
        threshold=community_report_service.COMMUNITY_FLAG_THRESHOLD,
    )
