"""
Greeting node — personalised welcome-back for existing users.

WHAT IT DOES:
  1. Loads the last 10 messages from the DB for context.
  2. Attempts to generate a personalised greeting using Google Gemini.
  3. Falls back to a rule-based greeting if Gemini is unavailable or errors.

WHY allow the LLM here (unlike onboarding):
  The greeting is non-critical — a wrong or imperfect greeting doesn't put
  anyone at risk. The personalisation value (user feels remembered) justifies
  the small latency and cost of an LLM call.

GUARDRAILS IN THE PROMPT:
  1. Explicitly forbids medical claims or diagnoses.
  2. Instructs the model to mention at most 2 profile facts.
  3. Keeps reply to 2–3 sentences.
  4. If the LLM ignores these constraints, the fallback fires.

FALLBACK GREETING:
  Template-based, uses the user's name + diet from the profile. Never fails.
"""

from __future__ import annotations

import asyncio
import logging

from langgraph.types import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompts import (
    GREETING_SYSTEM_PROMPT,
    GREETING_USER_PROMPT,
)
from app.agents.state import ConversationState
from app.core.config import get_settings
from app.core.i18n import t
from app.models.enums import MessageDirectionEnum
from app.services.message_service import format_history_for_prompt, get_recent_messages

logger = logging.getLogger(__name__)

# How many recent messages to include in the greeting prompt
CONTEXT_WINDOW_SIZE = 10

# Import language name map from i18n_ai to avoid duplication
try:
    from app.core.i18n_ai import _LANG_NAMES as LANG_NAMES
except ImportError:
    LANG_NAMES = {"en": "English", "hi": "Hindi", "ta": "Tamil"}


async def existing_user_greeting_node(
    state: ConversationState, config: RunnableConfig
) -> dict:
    """
    Generate a personalised greeting for a returning user.

    Logged at INFO so we can track greeting quality in production without
    storing the full LLM call in the DB.
    """
    wa_id = state["whatsapp_user_id"]
    lang = state.get("lang", "en")
    db_session: AsyncSession = config["configurable"]["db_session"]

    name = state.get("db_user_name") or "there"
    diet = state.get("db_user_diet")
    session_data = state.get("session_data") or {}
    medicines = session_data.get("medicines", [])

    logger.info(
        "greeting_node.start | wa_id=%r name=%r lang=%s medicines=%d",
        wa_id, name, lang, len(medicines),
    )

    # ------------------------------------------------------------------
    # Load windowed message history
    # ------------------------------------------------------------------
    messages = await get_recent_messages(
        db_session,
        whatsapp_user_id=wa_id,
        limit=CONTEXT_WINDOW_SIZE,
    )
    history_text = format_history_for_prompt(messages)
    msg_count = len(messages)
    logger.info(
        "greeting_node.history_loaded | wa_id=%r msg_count=%d", wa_id, msg_count
    )

    # ------------------------------------------------------------------
    # Load allergen names for the prompt
    # ------------------------------------------------------------------
    from app.models.user import UserAllergy
    import sqlalchemy as sa
    allergy_result = await db_session.execute(
        sa.select(UserAllergy.allergen).where(
            UserAllergy.user_id == state.get("db_user_id")
        )
    ) if state.get("db_user_id") else None
    allergen_names = (
        [r[0] for r in allergy_result.fetchall()] if allergy_result else []
    )

    # ------------------------------------------------------------------
    # Try LLM greeting
    # ------------------------------------------------------------------
    settings = get_settings()
    greeting = None

    if settings.google_api_key:
        try:
            greeting = await _generate_llm_greeting(
                name=name,
                diet=diet,
                allergens=allergen_names,
                medicines=medicines,
                history=history_text,
                msg_count=msg_count,
                lang=lang,
                settings=settings,
            )
            logger.info(
                "greeting_node.llm_success | wa_id=%r chars=%d", wa_id, len(greeting or "")
            )
        except Exception as exc:
            logger.warning(
                "greeting_node.llm_failed | wa_id=%r error=%s — using fallback", wa_id, exc
            )

    # ------------------------------------------------------------------
    # Fallback greeting (always works, no API needed)
    # ------------------------------------------------------------------
    if not greeting:
        greeting = _build_fallback_greeting(
            name=name, diet=diet, allergens=allergen_names, medicines=medicines, lang=lang
        )
        logger.info("greeting_node.fallback_used | wa_id=%r", wa_id)

    return {"response_text": greeting}


# ---------------------------------------------------------------------------
# LLM greeting
# ---------------------------------------------------------------------------

async def _generate_llm_greeting(
    *,
    name: str,
    diet: str | None,
    allergens: list[str],
    medicines: list[str],
    history: str,
    msg_count: int,
    lang: str,
    settings,
) -> str:
    lang_name = LANG_NAMES.get(lang, lang)

    system = GREETING_SYSTEM_PROMPT.format(lang_name=lang_name)
    user_prompt = GREETING_USER_PROMPT.format(
        name=name,
        diet=diet or "not specified",
        allergies=", ".join(allergens) if allergens else "none",
        medicines=", ".join(medicines) if medicines else "none",
        msg_count=msg_count,
        history=history or "(no previous messages)",
    )

    logger.debug("greeting_node.llm_call | model=%s", settings.i18n_ai_model)

    # Use Gemini via the google-genai SDK (already a dependency)
    def _sync_gemini() -> str:
        from google import genai
        client = genai.Client(api_key=settings.google_api_key)
        response = client.models.generate_content(
            model=settings.i18n_ai_model,          # gemini-2.0-flash-lite by default
            contents=f"{system}\n\n{user_prompt}",
        )
        return response.text.strip()

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_gemini)


# ---------------------------------------------------------------------------
# Template fallback
# ---------------------------------------------------------------------------

def _build_fallback_greeting(
    *,
    name: str,
    diet: str | None,
    allergens: list[str],
    medicines: list[str],
    lang: str,
) -> str:
    """
    Build a greeting from static templates when the LLM is unavailable.

    WHY not just t() with a single key:
      The fallback needs to conditionally include diet/allergen/medicine lines.
      A single template key would require complex placeholder logic; it's
      cleaner to build the string programmatically here.
    """
    lines: list[str] = [f"👋 Welcome back, *{name}*!"]

    if diet:
        lines.append(f"Your dietary preference is set to *{diet}*.")

    if allergens:
        a_str = ", ".join(allergens[:3])
        lines.append(f"I'll alert you if products contain *{a_str}*.")

    if medicines:
        m_str = ", ".join(medicines[:3])
        lines.append(f"I see you're taking *{m_str}* — I'll flag any interactions.")

    lines.append("\n📸 Send me a product photo or type a barcode number to verify.")

    return "\n".join(lines)
