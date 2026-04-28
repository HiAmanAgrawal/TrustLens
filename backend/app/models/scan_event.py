"""
MedicineScanEvent — audit log of every product scan.

WHY a dedicated events table instead of updating medicine_batches.is_verified:
  - Every scan is an immutable audit record — we never delete or update events.
  - Multiple users can scan the same batch; each gets their own event row.
  - The verdict may differ across scans (e.g., a batch expires between two scans).
  - Aggregate analytics (scan count, SUSPICIOUS rate, geography) run on this table.

user_id is nullable to support anonymous / WhatsApp pre-login scans.
medicine_id / batch_id are nullable because the scan may fail to identify the product.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col, uuid_pk
from app.models.enums import AuthenticityVerdictEnum

if TYPE_CHECKING:
    from app.models.medicine import Medicine, MedicineBatch
    from app.models.user import User


class MedicineScanEvent(Base):
    __tablename__ = "medicine_scan_events"

    id: Mapped[uuid_pk]
    # Nullable — anonymous scans are valid (WhatsApp users before onboarding)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Nullable — product may be unknown at scan time
    medicine_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("medicines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Nullable — batch may not be identified
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("medicine_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # The wall-clock time the user scanned the product (may differ from created_at
    # if events are batched/delayed, e.g., offline mobile sync)
    scanned_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    # Raw decoded barcode / QR string before product resolution
    barcode_data: Mapped[str | None] = mapped_column(sa.String(500))
    # OCR'd label text (truncated if > 5000 chars to save storage)
    ocr_text: Mapped[str | None] = mapped_column(sa.Text)
    authenticity_verdict: Mapped[AuthenticityVerdictEnum] = mapped_column(
        sa.Enum(AuthenticityVerdictEnum, name="authenticity_verdict_enum"),
        nullable=False,
        index=True,
    )
    # 0–10 score from the matcher engine; stored for analytics / threshold tuning
    verdict_score: Mapped[float | None] = mapped_column(sa.Numeric(4, 2))
    # Full structured verdict details as returned by the matcher (for replay / debugging)
    verdict_details: Mapped[dict | None] = mapped_column(JSONB)
    # Two-letter ISO country code from IP geolocation; for India-level analytics
    country_code: Mapped[str | None] = mapped_column(sa.String(2))
    created_at: Mapped[created_at_col]

    user: Mapped["User | None"] = relationship("User", back_populates="scan_events")
    medicine: Mapped["Medicine | None"] = relationship("Medicine", back_populates="scan_events")
    batch: Mapped["MedicineBatch | None"] = relationship(
        "MedicineBatch", back_populates="scan_events"
    )

    __table_args__ = (
        sa.Index("ix_scan_events_user_id", "user_id"),
        sa.Index("ix_scan_events_medicine_id", "medicine_id"),
        sa.Index("ix_scan_events_batch_id", "batch_id"),
        sa.Index("ix_scan_events_verdict", "authenticity_verdict"),
        sa.Index("ix_scan_events_scanned_at", "scanned_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<MedicineScanEvent id={self.id} verdict={self.authenticity_verdict} "
            f"user={self.user_id} medicine={self.medicine_id}>"
        )
