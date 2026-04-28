"""Prescription CRUD endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DBSession
from app.schemas.common import TrustLensResponse
from app.schemas.prescription import PrescriptionCreate, PrescriptionRead, PrescriptionUpdate
from app.services import prescription_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=TrustLensResponse[PrescriptionRead], status_code=status.HTTP_201_CREATED)
async def create_prescription(
    payload: PrescriptionCreate, session: DBSession, current_user: CurrentUser
):
    logger.info("POST /v1/prescriptions | user_id=%s", current_user.id)
    prescription = await prescription_service.create_prescription(
        session, current_user.id, payload
    )
    return TrustLensResponse.success(PrescriptionRead.model_validate(prescription))


@router.get("", response_model=TrustLensResponse[list[PrescriptionRead]])
async def list_prescriptions(session: DBSession, current_user: CurrentUser):
    logger.info("GET /v1/prescriptions | user_id=%s", current_user.id)
    prescriptions = await prescription_service.list_prescriptions(session, current_user.id)
    return TrustLensResponse.success(
        [PrescriptionRead.model_validate(p) for p in prescriptions]
    )


@router.get("/{prescription_id}", response_model=TrustLensResponse[PrescriptionRead])
async def get_prescription(
    prescription_id: uuid.UUID, session: DBSession, current_user: CurrentUser
):
    logger.info("GET /v1/prescriptions/%s", prescription_id)
    prescription = await prescription_service.get_prescription(
        session, prescription_id, current_user.id
    )
    return TrustLensResponse.success(PrescriptionRead.model_validate(prescription))


@router.delete("/{prescription_id}", response_model=TrustLensResponse[PrescriptionRead])
async def deactivate_prescription(
    prescription_id: uuid.UUID, session: DBSession, current_user: CurrentUser
):
    logger.info("DELETE /v1/prescriptions/%s", prescription_id)
    prescription = await prescription_service.deactivate_prescription(
        session, prescription_id, current_user.id
    )
    return TrustLensResponse.success(PrescriptionRead.model_validate(prescription))
