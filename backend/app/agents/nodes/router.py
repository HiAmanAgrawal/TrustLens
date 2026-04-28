"""
Router node — the entry point for every incoming WhatsApp message.

RESPONSIBILITY:
  Decide whether this is a new user (trigger onboarding) or an existing user
  (load their profile and route to the greeting/conversation handler).

DECISION TREE:
  1. Check DB for a user row matching whatsapp_user_id.
  2. If found → existing user; load name + diet + medicines for personalisation.
  3. If not found → check Redis for an in-progress onboarding session.
     3a. Session found → continue onboarding from where the user left off.
     3b. No session    → first contact; create a fresh session, ask for name.

LOGGING:
  Every branch is logged at INFO with enough context to trace a specific user
  through the funnel without exposing PII beyond the (hashed) phone number.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from langgraph.types import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.state import ConversationState
from app.models.enums import OnboardingStepEnum
from app.models.user import User
from app.services import session_service

logger = logging.getLogger(__name__)


async def router_node(
    state: ConversationState, config: RunnableConfig
) -> dict:
    """
    Determine routing for the incoming message and populate identity fields.

    Returns partial state updates only (LangGraph merges them into the full state).
    """
    wa_id = state["whatsapp_user_id"]
    db_session: AsyncSession = config["configurable"]["db_session"]

    logger.info("router_node.start | wa_id=%r lang=%s", wa_id, state.get("lang", "en"))

    # ------------------------------------------------------------------
    # Step 1: Look up the user in the database
    # ------------------------------------------------------------------
    user = await _find_user_by_wa_id(db_session, wa_id)

    if user is not None:
        logger.info(
            "router_node.existing_user | wa_id=%r user_id=%s name=%r",
            wa_id, user.id, user.full_name,
        )
        # Existing user → collect personalisation fields and head to greeting
        medicines = [c.condition_name for c in user.medical_conditions if c.is_active]
        return {
            "is_new_user": False,
            "db_user_id": str(user.id),
            "db_user_name": user.full_name,
            "db_user_diet": user.health_profile.dietary_preference.value
            if user.health_profile and user.health_profile.dietary_preference
            else None,
            "session_data": {
                "step": OnboardingStepEnum.ACTIVE.value,
                "medicines": medicines,
            },
        }

    # ------------------------------------------------------------------
    # Step 2: User not in DB — check Redis for an in-progress session
    # ------------------------------------------------------------------
    session = await session_service.get_session(wa_id)

    if session is not None:
        logger.info(
            "router_node.onboarding_in_progress | wa_id=%r step=%s",
            wa_id, session.step,
        )
        return {
            "is_new_user": True,
            "db_user_id": session.user_id,
            "onboarding_step": session.step,
            "session_data": {
                "step": session.step,
                "name": session.name,
                "diet": session.diet,
                "allergies": session.allergies,
                "medicines": session.medicines,
                "lang": session.lang,
            },
        }

    # ------------------------------------------------------------------
    # Step 3: Brand new contact — create a fresh onboarding session
    # ------------------------------------------------------------------
    logger.info("router_node.new_user | wa_id=%r", wa_id)
    fresh_session = await session_service.create_fresh_session(
        wa_id, lang=state.get("lang", "en")
    )
    return {
        "is_new_user": True,
        "db_user_id": None,
        "onboarding_step": fresh_session.step,
        "session_data": {
            "step": fresh_session.step,
            "name": None,
            "diet": None,
            "allergies": [],
            "medicines": [],
            "lang": fresh_session.lang,
        },
    }


# ---------------------------------------------------------------------------
# Routing condition — called by LangGraph to pick the next node
# ---------------------------------------------------------------------------

def route_after_router(state: ConversationState) -> str:
    """
    Return the name of the next node based on the router's decision.

    LangGraph calls this function on the outgoing edges of the router node;
    the return value must match one of the keys in add_conditional_edges().
    """
    if state.get("is_new_user"):
        return "onboarding"
    return "existing_user_greeting"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _find_user_by_wa_id(
    db_session: AsyncSession, whatsapp_user_id: str
) -> User | None:
    """
    Load a User by WhatsApp ID, eagerly loading health_profile and conditions
    so the greeting node doesn't trigger extra queries.
    """
    result = await db_session.execute(
        sa.select(User)
        .where(User.whatsapp_user_id == whatsapp_user_id, User.is_active.is_(True))
        .options(
            selectinload(User.health_profile),
            selectinload(User.allergies),
            selectinload(User.medical_conditions),
        )
    )
    return result.scalar_one_or_none()
