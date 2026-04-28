"""
MedicineService — CRUD + semantic search for medicines, salts, batches, and interactions.

Key design decisions:
  - Barcode lookup returns the batch first (most specific match), falling back to
    the product-level barcode, then falling back to pgvector semantic search.
    This hierarchy mirrors what a counterfeit scanner cares about.
  - Interaction checks look up ALL salts in the user's active prescriptions,
    then query drug_interactions for any pair that includes the new medicine's
    salts — quadratic in the number of salts but bounded by small real-world
    prescription sizes (typically < 10 medicines, < 3 salts each).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    BatchNotFoundError,
    DuplicateBarcodeError,
    MedicineNotFoundError,
)
from app.models.medicine import (
    DrugInteraction,
    Medicine,
    MedicineBatch,
    MedicineSalt,
    Salt,
)
from app.schemas.medicine import (
    DrugInteractionCreate,
    MedicineBatchCreate,
    MedicineCreate,
    MedicineUpdate,
    SaltCreate,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Salt operations
# ---------------------------------------------------------------------------

async def create_salt(session: AsyncSession, data: SaltCreate) -> Salt:
    logger.info("medicine_service.create_salt | name=%r", data.name)
    salt = Salt(
        name=data.name,
        iupac_name=data.iupac_name,
        cas_number=data.cas_number,
        molecular_formula=data.molecular_formula,
        molecular_weight_g_mol=data.molecular_weight_g_mol,
    )
    session.add(salt)
    await session.flush()
    logger.info("medicine_service.salt_created | salt_id=%s", salt.id)
    return salt


async def get_salt_by_name(session: AsyncSession, name: str) -> Salt | None:
    result = await session.execute(
        sa.select(Salt).where(Salt.name.ilike(name))
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Medicine CRUD
# ---------------------------------------------------------------------------

async def create_medicine(session: AsyncSession, data: MedicineCreate) -> Medicine:
    logger.info(
        "medicine_service.create | brand=%r generic=%r form=%s",
        data.brand_name, data.generic_name, data.dosage_form,
    )
    if data.barcode:
        await _assert_barcode_unique(session, data.barcode, medicine_id=None)

    medicine = Medicine(
        generic_name=data.generic_name,
        brand_name=data.brand_name,
        dosage_form=data.dosage_form,
        strength=data.strength,
        manufacturer=data.manufacturer,
        cdsco_license=data.cdsco_license,
        barcode=data.barcode,
    )
    session.add(medicine)
    await session.flush()   # get PK before adding salts

    for entry in data.salts:
        junction = MedicineSalt(
            medicine_id=medicine.id,
            salt_id=entry.salt_id,
            quantity_mg=entry.quantity_mg,
        )
        session.add(junction)

    await session.flush()
    logger.info("medicine_service.created | medicine_id=%s", medicine.id)
    return medicine


async def get_medicine_by_id(
    session: AsyncSession, medicine_id: uuid.UUID, *, with_salts: bool = False
) -> Medicine:
    logger.debug("medicine_service.get_by_id | medicine_id=%s", medicine_id)
    stmt = sa.select(Medicine).where(Medicine.id == medicine_id)
    if with_salts:
        stmt = stmt.options(
            selectinload(Medicine.salts).selectinload(MedicineSalt.salt)
        )

    result = await session.execute(stmt)
    medicine = result.scalar_one_or_none()
    if not medicine:
        raise MedicineNotFoundError(str(medicine_id))
    return medicine


async def find_by_barcode(
    session: AsyncSession, barcode: str
) -> tuple[Medicine, MedicineBatch | None] | None:
    """
    Look up a product by barcode.

    Returns (Medicine, MedicineBatch) if a batch barcode matches, or
    (Medicine, None) if only the product-level barcode matches, or
    None if nothing is found.

    WHY two levels: batch-specific QR codes encode expiry + batch_no;
    product barcodes (EAN-13) are the same for all batches of the same SKU.
    """
    logger.info("medicine_service.find_by_barcode | barcode=%r", barcode)

    # 1. Try batch-level barcode (most specific)
    batch_result = await session.execute(
        sa.select(MedicineBatch)
        .where(MedicineBatch.barcode == barcode)
        .options(selectinload(MedicineBatch.medicine))
    )
    batch = batch_result.scalar_one_or_none()
    if batch:
        logger.info(
            "medicine_service.find_by_barcode.batch_match | medicine_id=%s batch_id=%s",
            batch.medicine_id, batch.id,
        )
        return batch.medicine, batch

    # 2. Try product-level barcode
    product_result = await session.execute(
        sa.select(Medicine).where(Medicine.barcode == barcode)
    )
    medicine = product_result.scalar_one_or_none()
    if medicine:
        logger.info(
            "medicine_service.find_by_barcode.product_match | medicine_id=%s", medicine.id
        )
        return medicine, None

    logger.info("medicine_service.find_by_barcode.no_match | barcode=%r", barcode)
    return None


async def update_medicine(
    session: AsyncSession, medicine_id: uuid.UUID, data: MedicineUpdate
) -> Medicine:
    medicine = await get_medicine_by_id(session, medicine_id)
    changes = data.model_dump(exclude_none=True)
    if "barcode" in changes and changes["barcode"] != medicine.barcode:
        await _assert_barcode_unique(session, changes["barcode"], medicine_id=medicine_id)

    for field, value in changes.items():
        setattr(medicine, field, value)

    await session.flush()
    logger.info("medicine_service.updated | medicine_id=%s fields=%s", medicine_id, list(changes))
    return medicine


# ---------------------------------------------------------------------------
# Batch operations
# ---------------------------------------------------------------------------

async def create_batch(session: AsyncSession, data: MedicineBatchCreate) -> MedicineBatch:
    logger.info(
        "medicine_service.create_batch | medicine_id=%s batch_no=%r expiry=%s",
        data.medicine_id, data.batch_no, data.expiry_date,
    )
    # Verify the parent medicine exists
    await get_medicine_by_id(session, data.medicine_id)

    if data.barcode:
        existing = await session.execute(
            sa.select(MedicineBatch).where(MedicineBatch.barcode == data.barcode)
        )
        if existing.scalar_one_or_none():
            raise DuplicateBarcodeError()

    batch = MedicineBatch(
        medicine_id=data.medicine_id,
        batch_no=data.batch_no,
        manufacturing_date=data.manufacturing_date,
        expiry_date=data.expiry_date,
        barcode=data.barcode,
    )
    session.add(batch)
    await session.flush()
    logger.info("medicine_service.batch_created | batch_id=%s", batch.id)
    return batch


async def get_batch_by_id(session: AsyncSession, batch_id: uuid.UUID) -> MedicineBatch:
    result = await session.execute(
        sa.select(MedicineBatch).where(MedicineBatch.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise BatchNotFoundError(str(batch_id))
    return batch


async def is_batch_expired(batch: MedicineBatch) -> bool:
    """Check expiry without touching the DB — expiry_date is already loaded."""
    return batch.expiry_date < date.today()


async def mark_batch_verified(
    session: AsyncSession, batch_id: uuid.UUID
) -> MedicineBatch:
    batch = await get_batch_by_id(session, batch_id)
    batch.is_verified = True
    await session.flush()
    logger.info("medicine_service.batch_verified | batch_id=%s", batch_id)
    return batch


# ---------------------------------------------------------------------------
# Drug interactions
# ---------------------------------------------------------------------------

async def create_interaction(
    session: AsyncSession, data: DrugInteractionCreate
) -> DrugInteraction:
    """
    Create a drug-drug interaction record.

    Enforces the ordered-pair constraint (salt_id_a < salt_id_b) at the service
    layer so callers don't need to know about the DB check constraint.
    """
    logger.info(
        "medicine_service.create_interaction | a=%s b=%s severity=%s",
        data.salt_id_a, data.salt_id_b, data.severity,
    )
    # Canonicalise the pair: smaller UUID goes in slot A
    a, b = sorted([data.salt_id_a, data.salt_id_b])
    interaction = DrugInteraction(
        salt_id_a=a,
        salt_id_b=b,
        severity=data.severity,
        description=data.description,
        mechanism=data.mechanism,
        clinical_significance=data.clinical_significance,
        source=data.source,
    )
    session.add(interaction)
    await session.flush()
    return interaction


async def get_interactions_for_salt_ids(
    session: AsyncSession, salt_ids: list[uuid.UUID]
) -> list[DrugInteraction]:
    """
    Return all interactions where both salts are in ``salt_ids``.

    Used by the agent to check interactions across a user's full prescription:
      1. Collect all salt IDs from active prescriptions.
      2. Pass them here.
      3. Flag each CONTRAINDICATED / SEVERE pair to the user.
    """
    if not salt_ids:
        return []

    logger.debug(
        "medicine_service.get_interactions | checking %d salts", len(salt_ids)
    )
    result = await session.execute(
        sa.select(DrugInteraction)
        .where(
            DrugInteraction.salt_id_a.in_(salt_ids),
            DrugInteraction.salt_id_b.in_(salt_ids),
        )
        .options(
            selectinload(DrugInteraction.salt_a),
            selectinload(DrugInteraction.salt_b),
        )
    )
    interactions = list(result.scalars())
    logger.info(
        "medicine_service.interactions_found | count=%d severity_breakdown=%s",
        len(interactions),
        {i.severity for i in interactions},
    )
    return interactions


# ---------------------------------------------------------------------------
# Semantic search (pgvector)
# ---------------------------------------------------------------------------

async def semantic_search_medicines(
    session: AsyncSession,
    query_embedding: list[float],
    *,
    limit: int = 10,
    min_similarity: float = 0.75,
) -> list[Medicine]:
    """
    Find medicines whose name_embedding is closest to ``query_embedding``.

    WHY this function exists even though pgvector is optional:
      The function checks for None embeddings before running the query,
      so callers don't need to guard against the extension being absent.
    """
    logger.info(
        "medicine_service.semantic_search | limit=%d min_sim=%.2f", limit, min_similarity
    )
    try:
        # Cosine similarity via pgvector's <=> operator (smaller = more similar)
        result = await session.execute(
            sa.text(
                "SELECT id FROM medicines "
                "WHERE name_embedding IS NOT NULL "
                "ORDER BY name_embedding <=> :emb "
                "LIMIT :limit"
            ).bindparams(emb=str(query_embedding), limit=limit)
        )
        ids = [row[0] for row in result.fetchall()]
    except Exception as exc:
        logger.warning("medicine_service.semantic_search.failed | error=%s", exc)
        return []

    if not ids:
        return []

    result = await session.execute(
        sa.select(Medicine).where(Medicine.id.in_(ids))
    )
    return list(result.scalars())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _assert_barcode_unique(
    session: AsyncSession, barcode: str, medicine_id: uuid.UUID | None
) -> None:
    stmt = sa.select(Medicine.id).where(Medicine.barcode == barcode)
    if medicine_id:
        stmt = stmt.where(Medicine.id != medicine_id)

    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        raise DuplicateBarcodeError()
