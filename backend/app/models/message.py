"""
ConversationMessage — persistent record of every WhatsApp exchange.

WHY persist messages:
  1. Windowed context: the existing-user greeting node loads the last 10
     messages to generate a personalised reply without hitting an LLM for
     every turn.
  2. Audit trail: we can replay the onboarding conversation for debugging
     and compliance.
  3. Analytics: message volume, onboarding drop-off rate, step where users
     abandon, all come from this table.

WHY whatsapp_user_id is stored alongside user_id:
  During onboarding the user row doesn't exist yet. We store messages under
  the WhatsApp sender ID and back-fill user_id in a single UPDATE once the
  user is created at the end of onboarding.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col, uuid_pk
from app.models.enums import MessageDirectionEnum, MessageTypeEnum

if TYPE_CHECKING:
    from app.models.user import User


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[uuid_pk]
    # user_id is NULL during onboarding (user not yet created); backfilled after.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Always present — the WhatsApp sender ID used to correlate pre-registration msgs.
    whatsapp_user_id: Mapped[str] = mapped_column(
        sa.String(100), nullable=False, index=True
    )
    direction: Mapped[MessageDirectionEnum] = mapped_column(
        sa.Enum(MessageDirectionEnum, name="message_direction_enum"),
        nullable=False,
        index=True,
    )
    message_type: Mapped[MessageTypeEnum] = mapped_column(
        sa.Enum(MessageTypeEnum, name="message_type_enum"),
        nullable=False,
        server_default="TEXT",
    )
    message_text: Mapped[str | None] = mapped_column(sa.Text)
    # Stores media URLs, MIME types, detected language, onboarding_step, etc.
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[created_at_col]

    user: Mapped["User | None"] = relationship("User", backref="messages")

    __table_args__ = (
        sa.Index("ix_conv_messages_wa_id_created", "whatsapp_user_id", "created_at"),
        sa.Index("ix_conv_messages_user_id_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ConversationMessage id={self.id} "
            f"dir={self.direction} wa={self.whatsapp_user_id!r}>"
        )
