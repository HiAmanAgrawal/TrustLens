"""HealthProfileService — upsert pattern for the 1:1 user health profile."""

from __future__ import annotations

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UserNotFoundError
from app.models.health_profile import UserHealthProfile
from app.models.user import User
from app.schemas.health_profile import UserHealthProfileCreate

logger = logging.getLogger(__name__)


async def create_or_update_health_profile(
    session: AsyncSession,
    user_id: uuid.UUID,
    data: UserHealthProfileCreate,
) -> UserHealthProfile:
    """
    Upsert the health profile for ``user_id``.

    WHY upsert instead of separate create/update:
      The 1:1 relationship means the profile either exists or it doesn't.
      Callers shouldn't need to check existence first — PUT semantics handle both.
    """
    logger.info("health_profile_service.upsert | user_id=%s", user_id)

    # Verify the user exists before touching the profile table
    user_check = await session.execute(sa.select(User.id).where(User.id == user_id))
    if not user_check.scalar_one_or_none():
        raise UserNotFoundError(str(user_id))

    result = await session.execute(
        sa.select(UserHealthProfile).where(UserHealthProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()

    changes = data.model_dump(exclude_none=False)  # include None to allow field clearing

    if profile:
        logger.info("health_profile_service.updating | user_id=%s", user_id)
        for field, value in changes.items():
            setattr(profile, field, value)
    else:
        logger.info("health_profile_service.creating | user_id=%s", user_id)
        profile = UserHealthProfile(user_id=user_id, **changes)
        session.add(profile)

    await session.flush()
    return profile


async def get_health_profile(
    session: AsyncSession, user_id: uuid.UUID
) -> UserHealthProfile:
    from app.core.exceptions import NotFoundError
    result = await session.execute(
        sa.select(UserHealthProfile).where(UserHealthProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise NotFoundError("No health profile found for this user. Create one first.")
    return profile
