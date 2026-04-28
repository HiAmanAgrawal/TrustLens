"""
MessageService — persist and retrieve WhatsApp conversation history.

RESPONSIBILITIES:
  1. Save every inbound and outbound message to conversation_messages.
  2. Load the last N messages for a given user (windowed context for greeting).
  3. Back-fill user_id on pre-registration messages once onboarding completes.

WHY persist messages immediately (not in a background task):
  The greeting node reads the last 10 messages to generate a personalized reply.
  If we defer persistence, the greeting could see stale context. Immediate flush
  ensures the current message is visible to subsequent reads in the same request.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MessageDirectionEnum, MessageTypeEnum
from app.models.message import ConversationMessage

logger = logging.getLogger(__name__)


async def save_message(
    session: AsyncSession,
    *,
    whatsapp_user_id: str,
    direction: MessageDirectionEnum,
    message_text: str | None,
    message_type: MessageTypeEnum = MessageTypeEnum.TEXT,
    user_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> ConversationMessage:
    """
    Persist one conversation turn.

    Called for BOTH the inbound user message and the outbound bot reply so
    the history table reflects the full conversation, not just one side.
    """
    msg = ConversationMessage(
        whatsapp_user_id=whatsapp_user_id,
        user_id=user_id,
        direction=direction,
        message_type=message_type,
        message_text=(message_text or "")[:4096],  # cap length for storage
        metadata_=metadata,
    )
    session.add(msg)
    await session.flush()

    logger.info(
        "message_service.saved | id=%s wa_id=%r dir=%s type=%s chars=%d",
        msg.id, whatsapp_user_id, direction.value, message_type.value,
        len(message_text or ""),
    )
    return msg


async def get_recent_messages(
    session: AsyncSession,
    *,
    whatsapp_user_id: str,
    limit: int = 10,
) -> list[ConversationMessage]:
    """
    Return the last ``limit`` messages for a user, ordered oldest → newest.

    WHY order oldest-first: the greeting LLM prompt uses chronological order
    so the model understands conversation progression, not reverse-time slices.
    """
    logger.debug(
        "message_service.get_recent | wa_id=%r limit=%d", whatsapp_user_id, limit
    )
    # Subquery: get the N most recent by created_at DESC
    subq = (
        sa.select(ConversationMessage.id)
        .where(ConversationMessage.whatsapp_user_id == whatsapp_user_id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(limit)
        .subquery()
    )
    # Outer query: return them in ascending order (oldest first)
    result = await session.execute(
        sa.select(ConversationMessage)
        .where(ConversationMessage.id.in_(sa.select(subq)))
        .order_by(ConversationMessage.created_at.asc())
    )
    messages = list(result.scalars())
    logger.debug(
        "message_service.get_recent.found | wa_id=%r count=%d", whatsapp_user_id, len(messages)
    )
    return messages


async def backfill_user_id(
    session: AsyncSession,
    *,
    whatsapp_user_id: str,
    user_id: uuid.UUID,
) -> int:
    """
    Set user_id on all pre-registration messages for this WhatsApp number.

    Called once at the end of onboarding when the user row is created.
    Returns the number of rows updated.
    """
    logger.info(
        "message_service.backfill | wa_id=%r user_id=%s", whatsapp_user_id, user_id
    )
    result = await session.execute(
        sa.update(ConversationMessage)
        .where(
            ConversationMessage.whatsapp_user_id == whatsapp_user_id,
            ConversationMessage.user_id.is_(None),
        )
        .values(user_id=user_id)
    )
    updated = result.rowcount
    logger.info(
        "message_service.backfill.done | wa_id=%r updated=%d", whatsapp_user_id, updated
    )
    return updated


def format_history_for_prompt(messages: list[ConversationMessage]) -> str:
    """
    Render conversation history as a plain-text block for inclusion in LLM prompts.

    Example output:
      [User] Hi
      [Bot]  Welcome to TrustLens! What's your name?
      [User] Rahul
    """
    lines: list[str] = []
    for msg in messages:
        speaker = "User" if msg.direction == MessageDirectionEnum.INBOUND else "Bot"
        text = (msg.message_text or "").strip()
        if text:
            lines.append(f"[{speaker}] {text}")
    return "\n".join(lines)
