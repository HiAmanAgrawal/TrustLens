"""
Community Report Service — crowd-sourced batch/product safety flags.

THRESHOLD RULE:
  If a (product_id, product_type, batch_id) accumulates ≥ THRESHOLD distinct
  reports, every report in that group is updated with is_auto_flagged=True and
  the current count snapshot is stored. This lets downstream callers query
  auto_flag status without an aggregation — just a boolean column.

ANONYMOUS REPORTS:
  user_id is nullable. WhatsApp reports arrive without an authenticated user.
  The unique constraint (user_id, product_id, batch_id) enforces one-per-user
  when user_id IS NOT NULL, but anonymous reports always insert new rows.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.community_report import CommunityReport
from app.models.enums import ProductTypeEnum, ReportTypeEnum

logger = logging.getLogger(__name__)

# Reports needed on a single (product, batch) to auto-flag it.
COMMUNITY_FLAG_THRESHOLD = 5


async def create_report(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    product_type: ProductTypeEnum | str,
    report_type: ReportTypeEnum | str,
    user_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
    description: str | None = None,
) -> CommunityReport:
    """
    Submit a community report for a product/batch.

    If the same authenticated user already submitted a report for the same
    (product, batch) the existing row is returned unchanged (idempotent).
    For anonymous reports a new row is always inserted.

    Automatically calls auto_flag_check() after insert.
    """
    if user_id is not None:
        stmt = select(CommunityReport).where(
            CommunityReport.user_id == user_id,
            CommunityReport.product_id == product_id,
            CommunityReport.batch_id == batch_id,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            logger.debug(
                "community_report.duplicate | user_id=%s product_id=%s",
                user_id, product_id,
            )
            return existing

    report = CommunityReport(
        user_id=user_id,
        product_id=product_id,
        product_type=product_type,
        batch_id=batch_id,
        report_type=report_type,
        description=description,
    )
    session.add(report)
    await session.flush()

    logger.info(
        "community_report.created | product_id=%s type=%s batch=%s user=%s",
        product_id, product_type, batch_id, user_id,
    )

    await auto_flag_check(session, product_id=product_id, product_type=product_type, batch_id=batch_id)
    return report


async def get_report_count(
    session: AsyncSession,
    product_id: uuid.UUID,
    product_type: ProductTypeEnum | str,
    batch_id: uuid.UUID | None = None,
) -> int:
    """
    Return the number of community reports for a product/batch.

    batch_id=None matches product-level reports (no batch).
    Passing a specific batch_id counts only batch-scoped reports.
    """
    filters = [
        CommunityReport.product_id == product_id,
        CommunityReport.product_type == product_type,
    ]
    if batch_id is not None:
        filters.append(CommunityReport.batch_id == batch_id)
    else:
        filters.append(CommunityReport.batch_id.is_(None))

    stmt = select(func.count()).select_from(CommunityReport).where(and_(*filters))
    result = await session.execute(stmt)
    return result.scalar_one()


async def is_community_flagged(
    session: AsyncSession,
    product_id: uuid.UUID,
    product_type: ProductTypeEnum | str,
    batch_id: uuid.UUID | None = None,
) -> bool:
    """
    True if any report for this product/batch has is_auto_flagged=True.

    Checks the denormalised flag rather than re-counting, so this is O(1)
    once auto_flag_check has run.
    """
    filters = [
        CommunityReport.product_id == product_id,
        CommunityReport.product_type == product_type,
        CommunityReport.is_auto_flagged == True,  # noqa: E712
    ]
    if batch_id is not None:
        filters.append(CommunityReport.batch_id == batch_id)

    stmt = select(func.count()).select_from(CommunityReport).where(and_(*filters))
    result = await session.execute(stmt)
    return result.scalar_one() > 0


async def auto_flag_check(
    session: AsyncSession,
    product_id: uuid.UUID,
    product_type: ProductTypeEnum | str,
    batch_id: uuid.UUID | None = None,
) -> bool:
    """
    Count reports and, if threshold is reached, stamp all matching rows
    with is_auto_flagged=True and the current count.

    Returns True if the threshold was crossed (even if already flagged).
    Called automatically by create_report().
    """
    count = await get_report_count(session, product_id, product_type, batch_id)

    if count < COMMUNITY_FLAG_THRESHOLD:
        return False

    filters = [
        CommunityReport.product_id == product_id,
        CommunityReport.product_type == product_type,
    ]
    if batch_id is not None:
        filters.append(CommunityReport.batch_id == batch_id)
    else:
        filters.append(CommunityReport.batch_id.is_(None))

    await session.execute(
        update(CommunityReport)
        .where(and_(*filters))
        .values(is_auto_flagged=True, flag_count_at_time=count)
    )
    logger.warning(
        "community_report.auto_flagged | product_id=%s type=%s batch=%s count=%d",
        product_id, product_type, batch_id, count,
    )
    return True


async def get_reports(
    session: AsyncSession,
    product_id: uuid.UUID,
    product_type: ProductTypeEnum | str,
    batch_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[CommunityReport]:
    """Return community reports for a product/batch, newest first."""
    filters = [
        CommunityReport.product_id == product_id,
        CommunityReport.product_type == product_type,
    ]
    if batch_id is not None:
        filters.append(CommunityReport.batch_id == batch_id)

    stmt = (
        select(CommunityReport)
        .where(and_(*filters))
        .order_by(CommunityReport.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
