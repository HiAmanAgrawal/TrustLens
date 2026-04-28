"""
ProductCertification — polymorphic across medicines and grocery items.

WHY polymorphic (product_id + product_type) rather than two separate tables
or two FK columns:
  - Adding a third product domain (e.g., cosmetics) requires zero schema changes.
  - Two FK columns (medicine_id, grocery_item_id) would both be nullable, making
    every query carry a "which FK is non-null?" check.
  - The tradeoff is that the DB cannot enforce referential integrity natively.
    We enforce it at the service layer with explicit existence checks before insert.

FOREIGN KEY note: PostgreSQL does not support FK constraints on polymorphic IDs.
  The application-level guard in CertificationService.create() handles this.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, uuid_pk
from app.models.enums import CertificationAuthorityEnum, ProductTypeEnum


class ProductCertification(Base):
    __tablename__ = "product_certifications"

    id: Mapped[uuid_pk]
    # Polymorphic product reference (medicine or grocery item UUID)
    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True), nullable=False, index=True
    )
    product_type: Mapped[ProductTypeEnum] = mapped_column(
        sa.Enum(ProductTypeEnum, name="product_type_enum"),
        nullable=False,
        index=True,
    )
    authority: Mapped[CertificationAuthorityEnum] = mapped_column(
        sa.Enum(CertificationAuthorityEnum, name="certification_authority_enum"),
        nullable=False,
    )
    license_number: Mapped[str] = mapped_column(sa.String(200), nullable=False, index=True)
    is_valid: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    valid_from: Mapped[date | None] = mapped_column(sa.Date)
    valid_until: Mapped[date | None] = mapped_column(sa.Date)
    # Timestamp when we last verified this licence against the issuing authority
    verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[created_at_col]

    __table_args__ = (
        # Composite index: the most common query is "give me all valid certs for product X"
        sa.Index("ix_product_certifications_product", "product_id", "product_type"),
        sa.Index("ix_product_certifications_authority", "authority"),
        sa.Index("ix_product_certifications_license", "license_number"),
        sa.UniqueConstraint(
            "product_id", "product_type", "authority", "license_number",
            name="uq_product_certification",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ProductCertification product={self.product_id} "
            f"type={self.product_type} authority={self.authority} "
            f"license={self.license_number!r} valid={self.is_valid}>"
        )
