"""
Grocery domain models.

grocery_items ──< grocery_ingredients    (1:M, normalized)

WHY ingredients are in a separate table:
  - Allergen matching requires a JOIN/WHERE on ingredient names, not
    an array-contains operator on a JSONB column. Index on allergen_category
    makes "find all items with PEANUTS" a fast B-tree lookup.
  - Future ML models can embed individual ingredients (not just the full
    ingredient list string) for better semantic allergen detection.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk
from app.models.enums import AllergenCategoryEnum

if TYPE_CHECKING:
    from app.models.certification import ProductCertification


class GroceryItem(Base):
    __tablename__ = "grocery_items"

    id: Mapped[uuid_pk]
    product_name: Mapped[str] = mapped_column(sa.String(400), nullable=False, index=True)
    brand_name: Mapped[str | None] = mapped_column(sa.String(300), index=True)
    # Food Safety and Standards Authority of India licence number
    fssai_license: Mapped[str | None] = mapped_column(sa.String(50), index=True)
    barcode: Mapped[str | None] = mapped_column(sa.String(100), unique=True, index=True)
    # Product category to drive UI routing (snacks, dairy, beverages, etc.)
    category: Mapped[str | None] = mapped_column(sa.String(100), index=True)
    # Energy per 100g in kcal — cached from the latest nutrition parse
    energy_kcal_per_100g: Mapped[float | None] = mapped_column(sa.Numeric(8, 2))
    # Vector embedding of the product name for semantic search
    name_embedding: Mapped[Any | None] = mapped_column(
        sa.Text,
        nullable=True,
        comment="pgvector Vector(1536); populated by embedding worker",
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    created_at: Mapped[created_at_col]
    updated_at: Mapped[updated_at_col]

    ingredients: Mapped[list["GroceryIngredient"]] = relationship(
        "GroceryIngredient", back_populates="grocery_item", cascade="all, delete-orphan"
    )
    certifications: Mapped[list["ProductCertification"]] = relationship(
        "ProductCertification",
        primaryjoin="and_(foreign(ProductCertification.product_id) == GroceryItem.id, "
                    "ProductCertification.product_type == 'grocery')",
        viewonly=True,
    )

    __table_args__ = (
        sa.Index("ix_grocery_items_name", "product_name"),
        sa.Index("ix_grocery_items_fssai", "fssai_license"),
        sa.Index("ix_grocery_items_barcode", "barcode"),
        sa.Index("ix_grocery_items_category", "category"),
    )

    def __repr__(self) -> str:
        return f"<GroceryItem id={self.id} name={self.product_name!r}>"


class GroceryIngredient(Base):
    """
    One row per ingredient per grocery item.

    quantity/unit are nullable because Indian packaged foods often list
    ingredients by descending weight proportion without explicit quantities.
    """

    __tablename__ = "grocery_ingredients"

    id: Mapped[uuid_pk]
    grocery_item_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("grocery_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ingredient_name: Mapped[str] = mapped_column(sa.String(400), nullable=False)
    quantity: Mapped[float | None] = mapped_column(sa.Numeric(10, 3))
    unit: Mapped[str | None] = mapped_column(sa.String(20))   # g, mg, ml, %
    # Auto-classified allergen category for fast lookups; null if not an allergen
    allergen_category: Mapped[AllergenCategoryEnum | None] = mapped_column(
        sa.Enum(AllergenCategoryEnum, name="allergen_category_enum"),
        index=True,
    )
    created_at: Mapped[created_at_col]

    grocery_item: Mapped["GroceryItem"] = relationship(
        "GroceryItem", back_populates="ingredients"
    )

    __table_args__ = (
        sa.Index("ix_grocery_ingredients_item_id", "grocery_item_id"),
        sa.Index("ix_grocery_ingredients_allergen", "allergen_category"),
    )

    def __repr__(self) -> str:
        return f"<GroceryIngredient item={self.grocery_item_id} ingredient={self.ingredient_name!r}>"
