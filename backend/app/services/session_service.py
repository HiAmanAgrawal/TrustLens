"""
Redis-backed onboarding session service.

WHY Redis instead of the existing in-memory session store (services/whatsapp/session.py):
  The in-memory store resets on every server restart, which means a user who
  sends "Hi" gets the welcome message, the server restarts, and when they reply
  with their name the session is gone — the bot asks for the name again.

  Redis gives us:
    1. Persistence across restarts.
    2. Shared state if we run multiple API pods.
    3. Configurable TTL (24 h default — user can come back next day and continue).

SESSION KEY SCHEMA:
  Redis hash key: "trustlens:onboarding:{whatsapp_user_id}"
  Value: JSON string of OnboardingSession dataclass
  TTL: SESSION_ONBOARDING_TTL_S (default 86400 = 24 h)

THREAD SAFETY:
  All operations are async and use the redis.asyncio client. A single aioredis
  connection pool is shared process-wide (created lazily by get_redis_client()).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field

from app.core.config import get_settings
from app.models.enums import OnboardingStepEnum

logger = logging.getLogger(__name__)

SESSION_ONBOARDING_TTL_S = 86_400   # 24 hours
_ONBOARDING_PREFIX = "trustlens:onboarding"

# ---------------------------------------------------------------------------
# Redis client singleton
# ---------------------------------------------------------------------------

_redis_client = None


async def get_redis_client():
    """Lazily create and return the shared async Redis client."""
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("session_service.redis.connected | url=%s", settings.redis_url)
    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection pool — call on app shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("session_service.redis.closed")


# ---------------------------------------------------------------------------
# Onboarding session dataclass
# ---------------------------------------------------------------------------

@dataclass
class OnboardingSession:
    """
    Mutable onboarding state stored in Redis per WhatsApp user.

    Each field maps to one conversation turn in the onboarding flow:
      AWAITING_NAME      → ask name
      AWAITING_DIET      → ask dietary preference
      AWAITING_ALLERGIES → ask food allergies
      AWAITING_MEDICINES → ask regular medicines
      COMPLETE           → user row created in DB; user_id is set
      ACTIVE             → fully-onboarded user (for subsequent visits)
    """
    step: str = OnboardingStepEnum.AWAITING_NAME.value
    name: str | None = None
    diet: str | None = None
    allergies: list[str] = field(default_factory=list)
    medicines: list[str] = field(default_factory=list)
    # Set once the user row is persisted to Postgres at the end of onboarding
    user_id: str | None = None
    # Detected language code from the first message (best-effort)
    lang: str = "en"


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

def _session_key(whatsapp_user_id: str) -> str:
    return f"{_ONBOARDING_PREFIX}:{whatsapp_user_id}"


async def get_session(whatsapp_user_id: str) -> OnboardingSession | None:
    """
    Load the onboarding session for a WhatsApp user.
    Returns None if no session exists (first contact).
    """
    redis = await get_redis_client()
    key = _session_key(whatsapp_user_id)
    raw = await redis.get(key)

    if raw is None:
        logger.debug("session_service.get | no_session wa_id=%r", whatsapp_user_id)
        return None

    try:
        data = json.loads(raw)
        session = OnboardingSession(**data)
        logger.debug(
            "session_service.get | wa_id=%r step=%s", whatsapp_user_id, session.step
        )
        return session
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning(
            "session_service.get.corrupt | wa_id=%r error=%s — resetting", whatsapp_user_id, exc
        )
        await redis.delete(key)
        return None


async def save_session(
    whatsapp_user_id: str, session: OnboardingSession
) -> None:
    """Persist the onboarding session to Redis with 24-hour TTL."""
    redis = await get_redis_client()
    key = _session_key(whatsapp_user_id)
    await redis.setex(key, SESSION_ONBOARDING_TTL_S, json.dumps(asdict(session)))
    logger.debug(
        "session_service.save | wa_id=%r step=%s", whatsapp_user_id, session.step
    )


async def delete_session(whatsapp_user_id: str) -> None:
    """Remove the onboarding session (called after onboarding completes or user resets)."""
    redis = await get_redis_client()
    await redis.delete(_session_key(whatsapp_user_id))
    logger.info("session_service.deleted | wa_id=%r", whatsapp_user_id)


async def create_fresh_session(
    whatsapp_user_id: str, *, lang: str = "en"
) -> OnboardingSession:
    """Create a brand-new onboarding session for a first-time user."""
    session = OnboardingSession(
        step=OnboardingStepEnum.AWAITING_NAME.value,
        lang=lang,
    )
    await save_session(whatsapp_user_id, session)
    logger.info(
        "session_service.created | wa_id=%r step=%s lang=%s",
        whatsapp_user_id, session.step, lang,
    )
    return session


async def advance_session(
    whatsapp_user_id: str,
    session: OnboardingSession,
    *,
    new_step: str,
    **updates,
) -> OnboardingSession:
    """
    Move the session to the next onboarding step and persist it.

    ``updates`` are keyword arguments that set fields on the session:
        advance_session(wa_id, session, new_step="awaiting_diet", name="Rahul")
    """
    session.step = new_step
    for key, value in updates.items():
        setattr(session, key, value)
    await save_session(whatsapp_user_id, session)
    logger.info(
        "session_service.advanced | wa_id=%r new_step=%s", whatsapp_user_id, new_step
    )
    return session
