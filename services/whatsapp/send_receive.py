"""Provider-agnostic WhatsApp send + receive.

The actual HTTP work is delegated to an adapter under ``adapters/``. This file
intentionally knows nothing about Twilio / Meta / Unipile internals — it only
defines the domain-level message shape and the dispatch entry points.

Currently wired to the **Twilio** adapter. To swap providers, change the
imports and adapter calls below — the rest of the codebase stays untouched.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import AsyncIterator, Literal

from services.whatsapp.adapters import twilio_wa as twilio_adapter

logger = logging.getLogger(__name__)


# A single, transport-neutral message shape. Adapters convert their wire
# payloads into this and back again — keeping the rest of the codebase
# provider-blind.
@dataclass(frozen=True)
class WhatsAppMessage:
    sender: str                            # E.164 phone number, e.g. "+919876543210"
    body: str | None                       # text content (may be None for media-only)
    media_url: str | None = None           # download URL (may need auth depending on provider)
    media_mime: str | None = None
    direction: Literal["in", "out"] = "in"


async def receive_messages() -> AsyncIterator[WhatsAppMessage]:
    """Yield inbound messages.

    For webhook-based providers (Twilio, Meta Cloud, Unipile) this is normally
    unused — the FastAPI webhook route ingests messages directly. We expose
    this hook for adapters that support polling (or for tests) so the calling
    code stays uniform.
    """
    raise NotImplementedError
    # The unreachable yield below is required so Python recognises this as an
    # async generator at type-check time.
    yield  # type: ignore[unreachable]


async def close() -> None:
    """Shut down adapter resources (call on app shutdown)."""
    await twilio_adapter.close()
