"""In-memory per-user session store for WhatsApp conversations.

Tracks the most recent verification verdict per phone number so follow-up
questions have context.  Sessions expire after ``TTL_SECONDS`` of inactivity.

This is deliberately simple (no Redis, no DB) — good enough for a hackathon.
Swap for a persistent store later if needed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# Sessions expire after 30 minutes of inactivity.
TTL_SECONDS: float = 30 * 60

# Phone → session mapping.
_sessions: dict[str, "Session"] = {}


@dataclass
class Session:
    """State kept per user between WhatsApp messages."""

    phone: str
    chat_id: str
    # Last verification result (raw dict from VerdictResponse.model_dump()).
    verdict: dict[str, Any] | None = None
    # Convenience copies so the LLM follow-up doesn't need to dig into ``verdict``.
    ocr_text: str | None = None
    page_text: str | None = None
    # Conversation history for multi-turn follow-ups.
    follow_ups: list[dict[str, str]] = field(default_factory=list)
    last_active: float = field(default_factory=time.time)


def get(phone: str) -> Session | None:
    """Return the session for *phone*, or ``None`` if expired / missing."""
    session = _sessions.get(phone)
    if session is None:
        return None
    if time.time() - session.last_active > TTL_SECONDS:
        _sessions.pop(phone, None)
        return None
    return session


def upsert(
    phone: str,
    *,
    chat_id: str,
    verdict: dict[str, Any] | None = None,
    ocr_text: str | None = None,
    page_text: str | None = None,
) -> Session:
    """Create or replace the session for *phone*."""
    session = Session(
        phone=phone,
        chat_id=chat_id,
        verdict=verdict,
        ocr_text=ocr_text,
        page_text=page_text,
        follow_ups=[],
        last_active=time.time(),
    )
    _sessions[phone] = session
    _evict_stale()
    return session


def touch(phone: str) -> None:
    """Bump the last-active timestamp for *phone*."""
    session = _sessions.get(phone)
    if session:
        session.last_active = time.time()


def add_follow_up(phone: str, role: str, content: str) -> None:
    """Append a follow-up exchange to the session's history."""
    session = _sessions.get(phone)
    if session:
        session.follow_ups.append({"role": role, "content": content})
        session.last_active = time.time()
        # Cap history to prevent unbounded growth.
        if len(session.follow_ups) > 20:
            session.follow_ups = session.follow_ups[-20:]


def _evict_stale() -> None:
    """Remove sessions older than TTL.  Called lazily on upsert."""
    now = time.time()
    stale = [k for k, v in _sessions.items() if now - v.last_active > TTL_SECONDS]
    for k in stale:
        del _sessions[k]
