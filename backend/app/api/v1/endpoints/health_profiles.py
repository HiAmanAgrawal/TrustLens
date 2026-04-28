"""Health profile endpoints (1:1 with user)."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DBSession
from app.schemas.common import TrustLensResponse
from app.schemas.health_profile import (
    UserHealthProfileCreate,
    UserHealthProfileRead,
    UserHealthProfileUpdate,
)
from app.services.health_profile_service import (
    create_or_update_health_profile,
    get_health_profile,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.put(
    "/{user_id}/health-profile",
    response_model=TrustLensResponse[UserHealthProfileRead],
    status_code=status.HTTP_200_OK,
)
async def upsert_health_profile(
    user_id: uuid.UUID,
    payload: UserHealthProfileCreate,
    session: DBSession,
    _: CurrentUser,
):
    """
    Create or replace the user's health profile.

    PUT semantics: a profile is created if absent, otherwise fully replaced.
    Individual fields can be nulled out by sending null explicitly.
    """
    logger.info("PUT /v1/users/%s/health-profile", user_id)
    profile = await create_or_update_health_profile(session, user_id, payload)
    return TrustLensResponse.success(UserHealthProfileRead.model_validate(profile))


@router.get(
    "/{user_id}/health-profile",
    response_model=TrustLensResponse[UserHealthProfileRead],
)
async def get_profile(user_id: uuid.UUID, session: DBSession, _: CurrentUser):
    logger.info("GET /v1/users/%s/health-profile", user_id)
    profile = await get_health_profile(session, user_id)
    return TrustLensResponse.success(UserHealthProfileRead.model_validate(profile))
