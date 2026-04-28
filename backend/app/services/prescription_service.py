"""
PrescriptionService — manage user prescriptions and retrieve active salt lists.

``get_active_salt_ids`` is the key function called by the agent before every
scan: it collects the IDs of all active-ingredient salts from the user's current
prescriptions, which are then passed to ``medicine_service.get_interactions_for_salt_ids``
to detect drug-drug interactions with the newly scanned product.
"""

from __future__ import annotations

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import PrescriptionNotFoundError
from app.models.medicine import MedicineSalt
from app.models.prescription import Prescription, PrescriptionItem
from app.schemas.prescription import PrescriptionCreate, PrescriptionUpdate

logger = logging.getLogger(__name__)


async def create_prescription(
    session: AsyncSession, user_id: uuid.UUID, data: PrescriptionCreate
) -> Prescription:
    logger.info(
        "prescription_service.create | user_id=%s doctor=%r items=%d",
        user_id, data.doctor_name, len(data.items),
    )
    prescription = Prescription(
        user_id=user_id,
        doctor_name=data.doctor_name,
        doctor_registration_no=data.doctor_registration_no,
        hospital_name=data.hospital_name,
        issued_date=data.issued_date,
        valid_until=data.valid_until,
        notes=data.notes,
    )
    session.add(prescription)
    await session.flush()

    for item_data in data.items:
        item = PrescriptionItem(
            prescription_id=prescription.id,
            medicine_id=item_data.medicine_id,
            dosage_instructions=item_data.dosage_instructions,
            intake_frequency=item_data.intake_frequency,
            duration_days=item_data.duration_days,
            quantity_prescribed=item_data.quantity_prescribed,
            notes=item_data.notes,
        )
        session.add(item)

    await session.flush()
    logger.info("prescription_service.created | prescription_id=%s", prescription.id)
    return prescription


async def get_prescription(
    session: AsyncSession, prescription_id: uuid.UUID, user_id: uuid.UUID
) -> Prescription:
    """Fetch a prescription by ID, scoped to the requesting user."""
    result = await session.execute(
        sa.select(Prescription)
        .where(
            Prescription.id == prescription_id,
            Prescription.user_id == user_id,
        )
        .options(
            selectinload(Prescription.items).selectinload(PrescriptionItem.medicine)
        )
    )
    prescription = result.scalar_one_or_none()
    if not prescription:
        raise PrescriptionNotFoundError(str(prescription_id))
    return prescription


async def list_prescriptions(
    session: AsyncSession, user_id: uuid.UUID, *, active_only: bool = True
) -> list[Prescription]:
    logger.debug(
        "prescription_service.list | user_id=%s active_only=%s", user_id, active_only
    )
    stmt = (
        sa.select(Prescription)
        .where(Prescription.user_id == user_id)
        .options(selectinload(Prescription.items))
        .order_by(Prescription.issued_date.desc())
    )
    if active_only:
        stmt = stmt.where(Prescription.is_active.is_(True))

    result = await session.execute(stmt)
    return list(result.scalars())


async def deactivate_prescription(
    session: AsyncSession, prescription_id: uuid.UUID, user_id: uuid.UUID
) -> Prescription:
    prescription = await get_prescription(session, prescription_id, user_id)
    prescription.is_active = False
    await session.flush()
    logger.info("prescription_service.deactivated | prescription_id=%s", prescription_id)
    return prescription


async def get_active_salt_ids(
    session: AsyncSession, user_id: uuid.UUID
) -> list[uuid.UUID]:
    """
    Return all salt IDs from the user's active prescriptions.

    Called before every scan so the agent can check drug-drug interactions
    between the scanned product's salts and what the user is already taking.

    WHY JOIN rather than loading the full object graph:
      We only need the salt IDs — loading full Prescription → PrescriptionItem
      → Medicine → MedicineSalt objects for an interaction check would pull
      many more rows and columns than necessary.
    """
    logger.info("prescription_service.get_active_salt_ids | user_id=%s", user_id)

    result = await session.execute(
        sa.select(MedicineSalt.salt_id)
        .join(PrescriptionItem, PrescriptionItem.medicine_id == MedicineSalt.medicine_id)
        .join(Prescription, Prescription.id == PrescriptionItem.prescription_id)
        .where(
            Prescription.user_id == user_id,
            Prescription.is_active.is_(True),
        )
        .distinct()
    )
    salt_ids = [row[0] for row in result.fetchall()]
    logger.info(
        "prescription_service.active_salts_found | user_id=%s count=%d",
        user_id, len(salt_ids),
    )
    return salt_ids
