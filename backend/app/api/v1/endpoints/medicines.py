"""Medicine, batch, salt, and drug-interaction endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DBSession
from app.schemas.common import TrustLensResponse
from app.schemas.medicine import (
    DrugInteractionCreate,
    DrugInteractionRead,
    MedicineBatchCreate,
    MedicineBatchRead,
    MedicineCreate,
    MedicineRead,
    MedicineReadWithSalts,
    MedicineUpdate,
    SaltCreate,
    SaltRead,
)
from app.services import medicine_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ---- Salts ----

@router.post("/salts", response_model=TrustLensResponse[SaltRead], status_code=status.HTTP_201_CREATED)
async def create_salt(payload: SaltCreate, session: DBSession, _: CurrentUser):
    logger.info("POST /v1/medicines/salts | name=%r", payload.name)
    salt = await medicine_service.create_salt(session, payload)
    return TrustLensResponse.success(SaltRead.model_validate(salt))


# ---- Medicines ----

@router.post("", response_model=TrustLensResponse[MedicineRead], status_code=status.HTTP_201_CREATED)
async def create_medicine(payload: MedicineCreate, session: DBSession, _: CurrentUser):
    logger.info("POST /v1/medicines | brand=%r", payload.brand_name)
    medicine = await medicine_service.create_medicine(session, payload)
    return TrustLensResponse.success(MedicineRead.model_validate(medicine))


@router.get("/{medicine_id}", response_model=TrustLensResponse[MedicineReadWithSalts])
async def get_medicine(medicine_id: uuid.UUID, session: DBSession):
    logger.info("GET /v1/medicines/%s", medicine_id)
    medicine = await medicine_service.get_medicine_by_id(session, medicine_id, with_salts=True)
    return TrustLensResponse.success(MedicineReadWithSalts.model_validate(medicine))


@router.patch("/{medicine_id}", response_model=TrustLensResponse[MedicineRead])
async def update_medicine(
    medicine_id: uuid.UUID, payload: MedicineUpdate, session: DBSession, _: CurrentUser
):
    logger.info("PATCH /v1/medicines/%s", medicine_id)
    medicine = await medicine_service.update_medicine(session, medicine_id, payload)
    return TrustLensResponse.success(MedicineRead.model_validate(medicine))


# ---- Batches ----

@router.post("/batches", response_model=TrustLensResponse[MedicineBatchRead], status_code=status.HTTP_201_CREATED)
async def create_batch(payload: MedicineBatchCreate, session: DBSession, _: CurrentUser):
    logger.info("POST /v1/medicines/batches | medicine_id=%s batch_no=%r", payload.medicine_id, payload.batch_no)
    batch = await medicine_service.create_batch(session, payload)
    return TrustLensResponse.success(MedicineBatchRead.model_validate(batch))


@router.post("/batches/{batch_id}/verify", response_model=TrustLensResponse[MedicineBatchRead])
async def verify_batch(batch_id: uuid.UUID, session: DBSession, _: CurrentUser):
    logger.info("POST /v1/medicines/batches/%s/verify", batch_id)
    batch = await medicine_service.mark_batch_verified(session, batch_id)
    return TrustLensResponse.success(MedicineBatchRead.model_validate(batch))


# ---- Drug Interactions ----

@router.post("/interactions", response_model=TrustLensResponse[DrugInteractionRead], status_code=status.HTTP_201_CREATED)
async def create_interaction(payload: DrugInteractionCreate, session: DBSession, _: CurrentUser):
    logger.info(
        "POST /v1/medicines/interactions | a=%s b=%s severity=%s",
        payload.salt_id_a, payload.salt_id_b, payload.severity,
    )
    interaction = await medicine_service.create_interaction(session, payload)
    return TrustLensResponse.success(DrugInteractionRead.model_validate(interaction))
