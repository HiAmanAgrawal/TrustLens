"""
FastAPI dependency functions.

Every dependency in this file is injected via ``Depends()`` in route signatures.
Keeping them here (rather than inline in route files) means a change in how we
get the DB session or the current user only needs to happen in one place.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

import sqlalchemy as sa
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_async_session
from app.core.exceptions import AuthenticationError
from app.models.user import User

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB session
# ---------------------------------------------------------------------------

# Type alias — import this in route files for clean signatures:
#   async def my_route(session: DBSession): ...
DBSession = Annotated[AsyncSession, Depends(get_async_session)]

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

AppSettings = Annotated[Settings, Depends(get_settings)]

# ---------------------------------------------------------------------------
# Current user (header-based, placeholder for real auth)
# ---------------------------------------------------------------------------

async def get_current_user(
    session: DBSession,
    x_user_id: Annotated[str | None, Header()] = None,
) -> User:
    """
    Resolve the authenticated user from the ``X-User-Id`` request header.

    WHY header-based for now:
      Phase 1 focuses on the data layer. A proper JWT/Supabase Auth integration
      belongs in Phase 3. Until then, routes that need a user accept the UUID
      in a header so frontend and WhatsApp webhook can be developed in parallel
      without blocking on auth.

    In production this MUST be replaced with JWT verification:
      1. Validate the Bearer token against Supabase Auth.
      2. Extract the sub claim (user UUID).
      3. Load the User row (or create if first login).
    """
    if not x_user_id:
        logger.warning("deps.get_current_user | missing X-User-Id header")
        raise HTTPException(status_code=401, detail="X-User-Id header is required.")

    try:
        user_id = uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-User-Id must be a valid UUID.")

    result = await session.execute(sa.select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive.")

    return user


# Optional — routes that work with or without a logged-in user
async def get_optional_user(
    session: DBSession,
    x_user_id: Annotated[str | None, Header()] = None,
) -> User | None:
    """Return the current user or None for routes that support anonymous access."""
    if not x_user_id:
        return None
    try:
        return await get_current_user(session, x_user_id)
    except HTTPException:
        return None


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
