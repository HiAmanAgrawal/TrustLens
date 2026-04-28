"""
CommunityReport — crowd-sourced product safety flags.

WHY this table exists:
  Manufacturer data and FSSAI checks give us supply-side truth. Community
  reports give us demand-side signals: batches that are actually circulating
  with problems the official data doesn't reflect yet.

THRESHOLD RULE (configurable via COMMUNITY_REPORT_THRESHOLD env var, default 5):
  If a single (product_id, product_type, batch_id) tuple accumulates ≥ N
  distinct reports, the batch is auto-marked ``is_auto_flagged = True``.
  The UI always shows a banner for auto-flagged products so users can make
  an informed decision even if TrustLens can't independently verify the claim.

ANONYMITY:
  user_id is nullable so anonymous WhatsApp reports are accepted without
  forcing onboarding. Authenticated reports (user_id present) carry more
  weight in aggregation queries.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base
from app.models.enums import ProductTypeEnum, ReportTypeEnum


class CommunityReport(Base):
    __tablename__ = "community_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Who reported — nullable so anonymous WhatsApp reports are stored.
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Which product (polymorphic — medicine_id or grocery_item_id)
    product_id   = Column(UUID(as_uuid=True), nullable=False, index=True)
    product_type = Column(Enum(ProductTypeEnum), nullable=False)

    # Optional batch scoping — batch-specific reports are more actionable
    # than product-level ones (same product, different batch could be fine).
    batch_id = Column(UUID(as_uuid=True), nullable=True)

    report_type = Column(Enum(ReportTypeEnum), nullable=False)
    description = Column(Text, nullable=True)

    # Populated by community_report_service after threshold is crossed.
    is_auto_flagged = Column(Boolean, nullable=False, default=False)
    flag_count_at_time = Column(Integer, nullable=True)   # snapshot of count when flagged

    # Admin-reviewed status (future: moderation workflow)
    is_verified   = Column(Boolean, nullable=False, default=False)
    verified_by   = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at   = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        # Fast count queries: "how many reports for product X, batch Y?"
        Index("ix_community_reports_product_batch", "product_id", "product_type", "batch_id"),
        # Prevent duplicate reports from same user for same product+batch
        # (one report per user per product per batch is enough signal).
        Index(
            "uq_community_report_user_product_batch",
            "user_id", "product_id", "batch_id",
            unique=True,
            postgresql_where="user_id IS NOT NULL",
        ),
    )
