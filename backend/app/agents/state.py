"""
LangGraph state definition for the TrustLens conversation agent.

WHY a flat TypedDict rather than nested dataclasses:
  LangGraph copies the state dict between nodes. A flat TypedDict is cheap to
  copy and straightforward to inspect in LangSmith traces. Nested objects would
  require custom serialisers.

DEPENDENCY INJECTION via ``config["configurable"]``:
  Resources that cannot be serialised (AsyncSession, Redis client) are NOT
  stored in the state. Instead, each node receives them through the LangGraph
  ``RunnableConfig`` configurable dict:

      config["configurable"]["db_session"]    → AsyncSession
      config["configurable"]["redis_client"]  → not needed directly (session_service handles it)

  The webhook handler injects these before ``graph.ainvoke()``.
"""

from __future__ import annotations

from typing import Any
from typing import TypedDict


class ConversationState(TypedDict):
    # ---- Inbound message ----
    whatsapp_user_id: str          # Twilio sender ID, e.g. "whatsapp:+919876543210"
    phone_number: str              # E.164, e.g. "+919876543210" (derived from sender ID)
    incoming_text: str | None      # Body of the message (None for media-only)
    incoming_media_url: str | None # First media URL if message is image/audio
    incoming_media_type: str | None
    lang: str                      # Detected or default language code

    # ---- Routing decision ----
    is_new_user: bool              # True → onboarding flow; False → existing user flow
    onboarding_step: str | None    # Current OnboardingStepEnum value from Redis

    # ---- User identity ----
    db_user_id: str | None         # UUID of the User row (if exists in DB)
    db_user_name: str | None       # User's name (loaded for personalisation)
    db_user_diet: str | None       # Dietary preference (for allergy cross-check)

    # ---- Onboarding accumulation ----
    session_data: dict[str, Any] | None  # Full OnboardingSession.asdict()

    # ---- Output ----
    response_text: str             # The reply to send back over WhatsApp
    response_sent: bool            # Set to True once Twilio confirms delivery
