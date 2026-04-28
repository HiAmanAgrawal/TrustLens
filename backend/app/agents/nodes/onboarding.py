"""
Onboarding node — handles ALL steps of the sequential onboarding flow.

WHY a single node instead of one per step:
  LangGraph nodes are called per graph invocation (= per incoming message).
  Since each WhatsApp message is a separate HTTP request, using one node with
  an internal dispatch table is cleaner than building 5 graph nodes for
  effectively the same "read step, respond, advance" pattern.

STATE MACHINE (per incoming message):

  AWAITING_NAME:
    Incoming = any text → parse as name → save → advance to AWAITING_DIET
    Response = "Thanks {name}! What's your diet?"

  AWAITING_DIET:
    Incoming = diet keyword → save → advance to AWAITING_ALLERGIES
    Incoming = unrecognised → ask again (don't advance)
    Response = "Do you have any allergies?"

  AWAITING_ALLERGIES:
    Incoming = list or "none" → save → advance to AWAITING_MEDICINES
    Response = "Do you take any regular medicines?"

  AWAITING_MEDICINES:
    Incoming = list or "none" → save → create user in DB → mark COMPLETE
    Response = "✅ You're all set, {name}!"

PERSISTENCE:
  Each advance() call writes the updated session to Redis immediately.
  If the server crashes mid-onboarding the user can come back and continue.
  The DB user row is only created once ALL steps are complete (AWAITING_MEDICINES done).
"""

from __future__ import annotations

import logging
import uuid

from langgraph.types import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.parsers import parse_allergies, parse_diet, parse_medicines, parse_name
from app.agents.prompts import (
    CATALOGUE_ADDITIONS,
    ONBOARDING_ASK_ALLERGIES_KEY,
    ONBOARDING_ASK_DIET_KEY,
    ONBOARDING_ASK_MEDICINES_KEY,
    ONBOARDING_COMPLETE_KEY,
    ONBOARDING_INVALID_DIET_KEY,
    ONBOARDING_WELCOME_KEY,
)
from app.agents.state import ConversationState
from app.core.i18n import t
from app.models.enums import OnboardingStepEnum
from app.services import session_service
from app.services.message_service import backfill_user_id
from app.services.user_service import (
    add_allergy,
    add_medical_condition,
    create_user,
)
from app.schemas.user import UserAllergyCreate, UserCreate, UserMedicalConditionCreate

logger = logging.getLogger(__name__)

# Ensure onboarding strings are in the i18n catalogue at import time.
# (The i18n loader reads from JSON files; these are the fallback defaults.)
def _ensure_onboarding_keys() -> None:
    from app.core.i18n import _catalogues
    en = _catalogues.get("en", {})
    for k, v in CATALOGUE_ADDITIONS.items():
        if k not in en:
            en[k] = v


# ---------------------------------------------------------------------------
# Main onboarding node
# ---------------------------------------------------------------------------

async def onboarding_node(
    state: ConversationState, config: RunnableConfig
) -> dict:
    """
    Process one inbound message and advance the onboarding state machine.

    Called on every incoming message from a new (non-DB) user.
    Returns a partial state update with ``response_text`` set.
    """
    _ensure_onboarding_keys()

    wa_id = state["whatsapp_user_id"]
    step = state.get("onboarding_step") or OnboardingStepEnum.AWAITING_NAME.value
    incoming = (state.get("incoming_text") or "").strip()
    lang = state.get("lang", "en")
    db_session: AsyncSession = config["configurable"]["db_session"]

    logger.info(
        "onboarding_node.start | wa_id=%r step=%s incoming=%r lang=%s",
        wa_id, step, incoming[:60], lang,
    )

    # Load the current session from Redis (already populated by router_node)
    session_data = state.get("session_data") or {}

    if step == OnboardingStepEnum.AWAITING_NAME.value:
        return await _handle_awaiting_name(wa_id, incoming, session_data, lang)

    elif step == OnboardingStepEnum.AWAITING_DIET.value:
        return await _handle_awaiting_diet(wa_id, incoming, session_data, lang)

    elif step == OnboardingStepEnum.AWAITING_ALLERGIES.value:
        return await _handle_awaiting_allergies(wa_id, incoming, session_data, lang)

    elif step == OnboardingStepEnum.AWAITING_MEDICINES.value:
        return await _handle_awaiting_medicines(
            wa_id, incoming, session_data, lang, db_session
        )

    else:
        # Should not happen — router_node guards against this
        logger.warning("onboarding_node.unknown_step | wa_id=%r step=%s", wa_id, step)
        return {"response_text": t(ONBOARDING_WELCOME_KEY, lang=lang)}


# ---------------------------------------------------------------------------
# Step handlers
# ---------------------------------------------------------------------------

# Greetings that should trigger the welcome intro rather than being saved as a name.
_GREETINGS = frozenset([
    "hi", "hello", "hey", "hii", "hiii", "helo", "heya", "hiya",
    "yo", "sup", "hai", "hai there", "hi there", "hello there",
    "namaste", "namaskar", "vanakkam", "salaam",
    "good morning", "good afternoon", "good evening", "good night",
    "gm", "gn", "start", "begin", "help", "test", "👋", "🙏",
])


async def _handle_awaiting_name(
    wa_id: str, incoming: str, session_data: dict, lang: str
) -> dict:
    """Parse and save the user's name; ask about diet."""
    if not incoming:
        return {"response_text": t(ONBOARDING_WELCOME_KEY, lang=lang)}

    # If the first message is a greeting, show the intro and ask for name
    # without consuming it as the name.
    if incoming.lower().strip().rstrip("!.?") in _GREETINGS:
        return {"response_text": t(ONBOARDING_WELCOME_KEY, lang=lang)}

    name = parse_name(incoming)
    logger.info("onboarding.name_parsed | wa_id=%r name=%r", wa_id, name)

    # Load and advance session
    session = await session_service.get_session(wa_id)
    if session is None:
        session = await session_service.create_fresh_session(wa_id, lang=lang)

    await session_service.advance_session(
        wa_id, session,
        new_step=OnboardingStepEnum.AWAITING_DIET.value,
        name=name,
    )

    diet_question = t(ONBOARDING_ASK_DIET_KEY, lang=lang, name=name)
    logger.info("onboarding.step_advanced | wa_id=%r → awaiting_diet", wa_id)
    return {
        "response_text": diet_question,
        "onboarding_step": OnboardingStepEnum.AWAITING_DIET.value,
    }


async def _handle_awaiting_diet(
    wa_id: str, incoming: str, session_data: dict, lang: str
) -> dict:
    """Parse diet preference; ask about allergies."""
    diet_enum = parse_diet(incoming)

    if diet_enum is None:
        logger.info("onboarding.diet_invalid | wa_id=%r input=%r", wa_id, incoming[:40])
        return {"response_text": t(ONBOARDING_INVALID_DIET_KEY, lang=lang)}

    logger.info("onboarding.diet_parsed | wa_id=%r diet=%s", wa_id, diet_enum.value)

    session = await session_service.get_session(wa_id)
    if session is None:
        session = await session_service.create_fresh_session(wa_id, lang=lang)

    await session_service.advance_session(
        wa_id, session,
        new_step=OnboardingStepEnum.AWAITING_ALLERGIES.value,
        diet=diet_enum.value,
    )

    logger.info("onboarding.step_advanced | wa_id=%r → awaiting_allergies", wa_id)
    return {
        "response_text": t(ONBOARDING_ASK_ALLERGIES_KEY, lang=lang),
        "onboarding_step": OnboardingStepEnum.AWAITING_ALLERGIES.value,
    }


async def _handle_awaiting_allergies(
    wa_id: str, incoming: str, session_data: dict, lang: str
) -> dict:
    """Parse allergy list; ask about regular medicines."""
    raw_names, _categories = parse_allergies(incoming)
    logger.info("onboarding.allergies_parsed | wa_id=%r count=%d", wa_id, len(raw_names))

    session = await session_service.get_session(wa_id)
    if session is None:
        session = await session_service.create_fresh_session(wa_id, lang=lang)

    await session_service.advance_session(
        wa_id, session,
        new_step=OnboardingStepEnum.AWAITING_MEDICINES.value,
        allergies=raw_names,
    )

    logger.info("onboarding.step_advanced | wa_id=%r → awaiting_medicines", wa_id)
    return {
        "response_text": t(ONBOARDING_ASK_MEDICINES_KEY, lang=lang),
        "onboarding_step": OnboardingStepEnum.AWAITING_MEDICINES.value,
    }


async def _handle_awaiting_medicines(
    wa_id: str,
    incoming: str,
    session_data: dict,
    lang: str,
    db_session: AsyncSession,
) -> dict:
    """
    Parse medicine list, create the user row, and complete onboarding.

    This is the most complex step because it creates three types of DB rows:
      1. User            — core identity row
      2. UserAllergy     — one row per parsed allergen
      3. UserHealthProfile — dietary preference
      4. UserMedicalCondition — one row per medicine (stored as a condition)

    WHY medicines as UserMedicalCondition:
      We don't have a medicine lookup at onboarding time (the user typed a name,
      not scanned a barcode). Storing as a condition lets the scan agent check
      interactions later when the user scans a barcode.
    """
    medicines = parse_medicines(incoming)
    logger.info("onboarding.medicines_parsed | wa_id=%r count=%d", wa_id, len(medicines))

    # Reload session from Redis (contains name, diet, allergies from previous steps)
    session = await session_service.get_session(wa_id)
    if session is None:
        logger.error("onboarding.session_lost | wa_id=%r — restarting", wa_id)
        await session_service.create_fresh_session(wa_id, lang=lang)
        return {"response_text": t(ONBOARDING_WELCOME_KEY, lang=lang)}

    name = session.name or "Friend"

    # ------------------------------------------------------------------
    # Create User in DB
    # ------------------------------------------------------------------
    logger.info("onboarding.creating_user | wa_id=%r name=%r", wa_id, name)
    try:
        user = await create_user(
            db_session,
            UserCreate(
                full_name=name,
                whatsapp_user_id=wa_id,
                # phone_number derived from wa_id (strip "whatsapp:" prefix)
                phone_number=wa_id.replace("whatsapp:", ""),
            ),
        )
        user_id = user.id
        logger.info("onboarding.user_created | wa_id=%r user_id=%s", wa_id, user_id)
    except Exception as exc:
        # Duplicate user (e.g., user restarts onboarding) — handle gracefully
        logger.warning("onboarding.create_user_failed | wa_id=%r error=%s", wa_id, exc)
        return {"response_text": "There was an issue creating your profile. Please try again by sending *Hi*."}

    # ------------------------------------------------------------------
    # Health profile (dietary preference)
    # ------------------------------------------------------------------
    if session.diet:
        try:
            from app.models.enums import DietaryPreferenceEnum
            from app.schemas.health_profile import UserHealthProfileCreate
            from app.services.health_profile_service import create_or_update_health_profile

            diet_enum = DietaryPreferenceEnum(session.diet)
            await create_or_update_health_profile(
                db_session,
                user_id,
                UserHealthProfileCreate(dietary_preference=diet_enum),
            )
            logger.info("onboarding.health_profile_created | user_id=%s diet=%s", user_id, diet_enum)
        except Exception as exc:
            logger.warning("onboarding.health_profile_failed | user_id=%s error=%s", user_id, exc)

    # ------------------------------------------------------------------
    # Allergies
    # ------------------------------------------------------------------
    for allergen_name in session.allergies:
        try:
            from app.agents.parsers import parse_allergies as _pa
            _raw, cats = _pa(allergen_name)
            cat = cats[0] if cats else None
            await add_allergy(
                db_session,
                user_id,
                UserAllergyCreate(allergen=allergen_name, allergen_category=cat),
            )
        except Exception as exc:
            logger.warning("onboarding.add_allergy_failed | allergen=%r error=%s", allergen_name, exc)

    logger.info("onboarding.allergies_saved | user_id=%s count=%d", user_id, len(session.allergies))

    # ------------------------------------------------------------------
    # Regular medicines (stored as medical conditions for interaction checks)
    # ------------------------------------------------------------------
    for med_name in medicines:
        try:
            await add_medical_condition(
                db_session,
                user_id,
                UserMedicalConditionCreate(condition_name=med_name),
            )
        except Exception as exc:
            logger.warning("onboarding.add_medicine_failed | med=%r error=%s", med_name, exc)

    logger.info("onboarding.medicines_saved | user_id=%s count=%d", user_id, len(medicines))

    # ------------------------------------------------------------------
    # Back-fill user_id on pre-registration messages
    # ------------------------------------------------------------------
    try:
        await backfill_user_id(db_session, whatsapp_user_id=wa_id, user_id=user_id)
    except Exception as exc:
        logger.warning("onboarding.backfill_failed | user_id=%s error=%s", user_id, exc)

    # ------------------------------------------------------------------
    # Mark session complete in Redis
    # ------------------------------------------------------------------
    await session_service.advance_session(
        wa_id, session,
        new_step=OnboardingStepEnum.COMPLETE.value,
        medicines=medicines,
        user_id=str(user_id),
    )

    complete_msg = t(ONBOARDING_COMPLETE_KEY, lang=lang, name=name)
    logger.info("onboarding.complete | wa_id=%r user_id=%s", wa_id, user_id)

    return {
        "response_text": complete_msg,
        "onboarding_step": OnboardingStepEnum.COMPLETE.value,
        "db_user_id": str(user_id),
        "db_user_name": name,
    }
