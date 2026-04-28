"""
Medicine domain models.

Table relationships:
  medicines ──< medicine_salts >── salts    (M:M via junction)
  medicines ──< medicine_batches            (1:M, batch-level identity)
  salts     ──< drug_interactions           (self-referential M:M via junction)
  users     ──< user_drug_reactions >── salts

WHY salts are a separate table:
  The same active ingredient (e.g., Paracetamol) appears in hundreds of brand
  medicines. Normalizing salts allows:
    1. Drug interaction checks to operate on salts, not brand names — no need
       to maintain a per-brand interaction table.
    2. pgvector semantic search on salt names for "did the user mean Paracetamol
       when they typed 'paracetamole'?"
    3. A single update to a salt's CAS number propagates to all medicines.

WHY barcode is on BOTH medicines AND medicine_batches:
  - medicines.barcode  → the product-level barcode printed on the outer box
                          (GS1 GTIN, same for all batches of the same SKU).
  - medicine_batches.barcode → the batch-specific 2D barcode / QR printed on the
                                blister/bottle, encodes batch_no + expiry.
  When we scan a barcode we check batches first (specific) then fall back to
  the product-level barcode (general).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk
from app.models.enums import DosageFormEnum, InteractionSeverityEnum, ReactionSeverityEnum

if TYPE_CHECKING:
    from app.models.certification import ProductCertification
    from app.models.prescription import PrescriptionItem
    from app.models.scan_event import MedicineScanEvent
    from app.models.user import User


# ---------------------------------------------------------------------------
# Salt (active pharmaceutical ingredient)
# ---------------------------------------------------------------------------

class Salt(Base):
    __tablename__ = "salts"

    id: Mapped[uuid_pk]
    name: Mapped[str] = mapped_column(sa.String(300), nullable=False, unique=True, index=True)
    iupac_name: Mapped[str | None] = mapped_column(sa.String(500))
    # Chemical Abstracts Service registry number — globally unique identifier
    # for a chemical substance; useful for cross-referencing with PubChem.
    cas_number: Mapped[str | None] = mapped_column(sa.String(20), unique=True)
    molecular_formula: Mapped[str | None] = mapped_column(sa.String(100))
    molecular_weight_g_mol: Mapped[float | None] = mapped_column(sa.Numeric(10, 4))
    created_at: Mapped[created_at_col]

    medicines: Mapped[list["MedicineSalt"]] = relationship("MedicineSalt", back_populates="salt")
    interactions_as_a: Mapped[list["DrugInteraction"]] = relationship(
        "DrugInteraction", foreign_keys="DrugInteraction.salt_id_a", back_populates="salt_a"
    )
    interactions_as_b: Mapped[list["DrugInteraction"]] = relationship(
        "DrugInteraction", foreign_keys="DrugInteraction.salt_id_b", back_populates="salt_b"
    )
    user_reactions: Mapped[list["UserDrugReaction"]] = relationship(
        "UserDrugReaction", back_populates="salt"
    )

    def __repr__(self) -> str:
        return f"<Salt name={self.name!r}>"


# ---------------------------------------------------------------------------
# Medicine (product-level, not batch-level)
# ---------------------------------------------------------------------------

class Medicine(Base):
    __tablename__ = "medicines"

    id: Mapped[uuid_pk]
    generic_name: Mapped[str] = mapped_column(sa.String(300), nullable=False, index=True)
    brand_name: Mapped[str] = mapped_column(sa.String(300), nullable=False, index=True)
    dosage_form: Mapped[DosageFormEnum] = mapped_column(
        sa.Enum(DosageFormEnum, name="dosage_form_enum"), nullable=False
    )
    # Strength as a free string to accommodate mixed units: "500mg", "10mg/5ml"
    strength: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    manufacturer: Mapped[str] = mapped_column(sa.String(300), nullable=False, index=True)
    # CDSCO Manufacturing Licence number (MDL/LIC format)
    cdsco_license: Mapped[str | None] = mapped_column(sa.String(100), index=True)
    # Product-level GS1 barcode (same across all batches)
    barcode: Mapped[str | None] = mapped_column(sa.String(100), unique=True, index=True)
    qr_data: Mapped[str | None] = mapped_column(sa.Text)
    # Embedding for semantic / fuzzy name search via pgvector.
    # Populated asynchronously after insert; NULL until the embedding job runs.
    name_embedding: Mapped[Any | None] = mapped_column(
        sa.Text,    # placeholder — overridden at table creation to Vector(1536)
        nullable=True,
        comment="pgvector Vector(1536); populated by embedding worker",
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    created_at: Mapped[created_at_col]
    updated_at: Mapped[updated_at_col]

    salts: Mapped[list["MedicineSalt"]] = relationship(
        "MedicineSalt", back_populates="medicine", cascade="all, delete-orphan"
    )
    batches: Mapped[list["MedicineBatch"]] = relationship(
        "MedicineBatch", back_populates="medicine", cascade="all, delete-orphan"
    )
    certifications: Mapped[list["ProductCertification"]] = relationship(
        "ProductCertification",
        primaryjoin="and_(foreign(ProductCertification.product_id) == Medicine.id, "
                    "ProductCertification.product_type == 'medicine')",
        viewonly=True,
    )
    prescription_items: Mapped[list["PrescriptionItem"]] = relationship(
        "PrescriptionItem", back_populates="medicine"
    )
    scan_events: Mapped[list["MedicineScanEvent"]] = relationship(
        "MedicineScanEvent", back_populates="medicine"
    )

    __table_args__ = (
        sa.Index("ix_medicines_generic_name", "generic_name"),
        sa.Index("ix_medicines_brand_name", "brand_name"),
        sa.Index("ix_medicines_cdsco", "cdsco_license"),
        sa.Index("ix_medicines_barcode", "barcode"),
    )

    def __repr__(self) -> str:
        return f"<Medicine id={self.id} brand={self.brand_name!r} strength={self.strength!r}>"


# ---------------------------------------------------------------------------
# Medicine ↔ Salt junction (with quantity)
# ---------------------------------------------------------------------------

class MedicineSalt(Base):
    """
    Junction table linking medicines to their active ingredients.

    quantity_mg is nullable because combination products (e.g., Paracetamol +
    Ibuprofen) sometimes don't disclose individual salt quantities on the label.
    """

    __tablename__ = "medicine_salts"

    id: Mapped[uuid_pk]
    medicine_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("medicines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    salt_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("salts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity_mg: Mapped[float | None] = mapped_column(sa.Numeric(10, 3))
    created_at: Mapped[created_at_col]

    medicine: Mapped["Medicine"] = relationship("Medicine", back_populates="salts")
    salt: Mapped["Salt"] = relationship("Salt", back_populates="medicines")

    __table_args__ = (
        sa.UniqueConstraint("medicine_id", "salt_id", name="uq_medicine_salts"),
        sa.Index("ix_medicine_salts_medicine_id", "medicine_id"),
        sa.Index("ix_medicine_salts_salt_id", "salt_id"),
    )


# ---------------------------------------------------------------------------
# Medicine Batch (batch-level identity)
# ---------------------------------------------------------------------------

class MedicineBatch(Base):
    """
    A single manufactured batch of a medicine.

    WHY batch-level rather than just product-level:
      Counterfeit detection requires comparing the scanned QR's batch number
      and expiry date against the manufacturer's official records. Storing
      batches as first-class entities enables:
        - Direct expiry checks (EXPIRED verdict)
        - Batch recall lookups
        - Verified flag set when CDSCO/scraper confirms the batch
    """

    __tablename__ = "medicine_batches"

    id: Mapped[uuid_pk]
    medicine_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("medicines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    batch_no: Mapped[str] = mapped_column(sa.String(100), nullable=False, index=True)
    manufacturing_date: Mapped[date | None] = mapped_column(sa.Date)
    expiry_date: Mapped[date] = mapped_column(sa.Date, nullable=False, index=True)
    # True when this batch has been cross-checked against official CDSCO/manufacturer data
    is_verified: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    # Batch-specific 2D barcode / QR data (encodes batch_no + expiry)
    barcode: Mapped[str | None] = mapped_column(sa.String(200), unique=True, index=True)
    qr_data: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[created_at_col]
    updated_at: Mapped[updated_at_col]

    medicine: Mapped["Medicine"] = relationship("Medicine", back_populates="batches")
    scan_events: Mapped[list["MedicineScanEvent"]] = relationship(
        "MedicineScanEvent", back_populates="batch"
    )

    __table_args__ = (
        sa.UniqueConstraint("medicine_id", "batch_no", name="uq_medicine_batch"),
        sa.Index("ix_medicine_batches_expiry", "expiry_date"),
        sa.Index("ix_medicine_batches_barcode", "barcode"),
    )

    def __repr__(self) -> str:
        return f"<MedicineBatch medicine={self.medicine_id} batch={self.batch_no!r} expiry={self.expiry_date}>"


# ---------------------------------------------------------------------------
# Drug Interactions
# ---------------------------------------------------------------------------

class DrugInteraction(Base):
    """
    Known interaction between two salts.

    WHY unordered pair:
      Drug A → Drug B and Drug B → Drug A are the same interaction.
      We enforce salt_id_a < salt_id_b (lexicographic UUID order) via a
      check constraint so duplicates are impossible and lookup only needs
      one WHERE clause.
    """

    __tablename__ = "drug_interactions"

    id: Mapped[uuid_pk]
    salt_id_a: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("salts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    salt_id_b: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("salts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    severity: Mapped[InteractionSeverityEnum] = mapped_column(
        sa.Enum(InteractionSeverityEnum, name="interaction_severity_enum"), nullable=False
    )
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    mechanism: Mapped[str | None] = mapped_column(sa.Text)
    clinical_significance: Mapped[str | None] = mapped_column(sa.Text)
    # Data provenance — "DrugBank", "openFDA", "manual"
    source: Mapped[str | None] = mapped_column(sa.String(100))
    created_at: Mapped[created_at_col]

    salt_a: Mapped["Salt"] = relationship(
        "Salt", foreign_keys=[salt_id_a], back_populates="interactions_as_a"
    )
    salt_b: Mapped["Salt"] = relationship(
        "Salt", foreign_keys=[salt_id_b], back_populates="interactions_as_b"
    )

    __table_args__ = (
        sa.UniqueConstraint("salt_id_a", "salt_id_b", name="uq_drug_interactions_pair"),
        sa.CheckConstraint(
            "salt_id_a < salt_id_b",
            name="ck_drug_interactions_ordered_pair",
        ),
        sa.Index("ix_drug_interactions_a", "salt_id_a"),
        sa.Index("ix_drug_interactions_b", "salt_id_b"),
        sa.Index("ix_drug_interactions_severity", "severity"),
    )

    def __repr__(self) -> str:
        return f"<DrugInteraction a={self.salt_id_a} b={self.salt_id_b} severity={self.severity}>"


# ---------------------------------------------------------------------------
# User-reported drug reactions (adverse events)
# ---------------------------------------------------------------------------

class UserDrugReaction(Base):
    """
    Adverse drug reaction reported by a user for a specific salt.

    WHY mapped to salt rather than medicine:
      The same adverse event (e.g., hives after Paracetamol) applies to all
      medicines containing that salt. Storing at salt level lets the agent
      flag all branded variants, not just the one the user originally used.

    SCOPE GUARDRAIL: We store the user's description verbatim. We do NOT
      infer a medical diagnosis, compute a risk score, or share data across
      users. This is purely a personal medication history log.
    """

    __tablename__ = "user_drug_reactions"

    id: Mapped[uuid_pk]
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    salt_id: Mapped[uuid.UUID] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("salts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reaction_description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    severity: Mapped[ReactionSeverityEnum] = mapped_column(
        sa.Enum(ReactionSeverityEnum, name="reaction_severity_enum"), nullable=False
    )
    reported_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    created_at: Mapped[created_at_col]

    user: Mapped["User"] = relationship("User", back_populates="drug_reactions")
    salt: Mapped["Salt"] = relationship("Salt", back_populates="user_reactions")

    __table_args__ = (
        sa.Index("ix_user_drug_reactions_user_id", "user_id"),
        sa.Index("ix_user_drug_reactions_salt_id", "salt_id"),
    )
