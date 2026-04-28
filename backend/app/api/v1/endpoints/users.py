"""
User management endpoints.

Routes follow the resource-oriented naming convention:
  POST   /v1/users                  — create
  GET    /v1/users/{user_id}         — read
  PATCH  /v1/users/{user_id}         — partial update
  DELETE /v1/users/{user_id}         — soft-delete
  POST   /v1/users/{user_id}/allergies
  DELETE /v1/users/{user_id}/allergies/{allergy_id}
  POST   /v1/users/{user_id}/conditions
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DBSession
from app.core.exceptions import TrustLensError
from app.schemas.common import TrustLensResponse
from app.schemas.user import (
    UserAllergyCreate,
    UserAllergyRead,
    UserCreate,
    UserMedicalConditionCreate,
    UserMedicalConditionRead,
    UserRead,
    UserReadWithProfile,
    UserUpdate,
)
from app.services import user_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=TrustLensResponse[UserRead], status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, session: DBSession):
    """Register a new user. At least one contact field (phone/email/WhatsApp) is required."""
    logger.info("POST /v1/users | name=%r", payload.full_name)
    user = await user_service.create_user(session, payload)
    return TrustLensResponse.success(UserRead.model_validate(user))


@router.get("/{user_id}", response_model=TrustLensResponse[UserReadWithProfile])
async def get_user(user_id: uuid.UUID, session: DBSession, _current: CurrentUser):
    """Fetch a user with their health profile, allergies, and medical conditions."""
    logger.info("GET /v1/users/%s", user_id)
    user = await user_service.get_user_by_id(session, user_id, with_profile=True)
    return TrustLensResponse.success(UserReadWithProfile.model_validate(user))


@router.patch("/{user_id}", response_model=TrustLensResponse[UserRead])
async def update_user(user_id: uuid.UUID, payload: UserUpdate, session: DBSession, _: CurrentUser):
    logger.info("PATCH /v1/users/%s", user_id)
    user = await user_service.update_user(session, user_id, payload)
    return TrustLensResponse.success(UserRead.model_validate(user))


@router.delete("/{user_id}", response_model=TrustLensResponse[UserRead])
async def deactivate_user(user_id: uuid.UUID, session: DBSession, _: CurrentUser):
    logger.info("DELETE /v1/users/%s", user_id)
    user = await user_service.deactivate_user(session, user_id)
    return TrustLensResponse.success(UserRead.model_validate(user))


# ---- Allergies ----

@router.post(
    "/{user_id}/allergies",
    response_model=TrustLensResponse[UserAllergyRead],
    status_code=status.HTTP_201_CREATED,
)
async def add_allergy(
    user_id: uuid.UUID, payload: UserAllergyCreate, session: DBSession, _: CurrentUser
):
    logger.info("POST /v1/users/%s/allergies | allergen=%r", user_id, payload.allergen)
    allergy = await user_service.add_allergy(session, user_id, payload)
    return TrustLensResponse.success(UserAllergyRead.model_validate(allergy))


@router.delete("/{user_id}/allergies/{allergy_id}", response_model=TrustLensResponse[None])
async def remove_allergy(
    user_id: uuid.UUID, allergy_id: uuid.UUID, session: DBSession, _: CurrentUser
):
    logger.info("DELETE /v1/users/%s/allergies/%s", user_id, allergy_id)
    await user_service.remove_allergy(session, user_id, allergy_id)
    return TrustLensResponse.success(None)


# ---- Medical conditions ----

@router.post(
    "/{user_id}/conditions",
    response_model=TrustLensResponse[UserMedicalConditionRead],
    status_code=status.HTTP_201_CREATED,
)
async def add_condition(
    user_id: uuid.UUID,
    payload: UserMedicalConditionCreate,
    session: DBSession,
    _: CurrentUser,
):
    logger.info("POST /v1/users/%s/conditions | condition=%r", user_id, payload.condition_name)
    condition = await user_service.add_medical_condition(session, user_id, payload)
    return TrustLensResponse.success(UserMedicalConditionRead.model_validate(condition))
