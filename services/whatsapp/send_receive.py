"""Provider-agnostic WhatsApp send + receive.

The actual HTTP work is delegated to an adapter under ``adapters/``. This file
intentionally knows nothing about Twilio / Meta / Unipile internals — it only
defines the domain-level message shape and the dispatch entry points.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Literal


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


async def send_message(to: str, body: str, media_url: str | None = None) -> None:
    """Send a WhatsApp message via the configured provider.

    TODO:
      - Read provider choice from settings.
      - Lazy-import the matching adapter so optional deps stay optional.
      - Surface adapter errors as a small, typed exception (not raw httpx).
    """
    _ = (to, body, media_url)
    raise NotImplementedError("Pick a provider and implement an adapter first.")


async def receive_messages() -> AsyncIterator[WhatsAppMessage]:
    """Yield inbound messages.

    For webhook-based providers (Twilio, Meta Cloud) this is normally unused —
    the FastAPI webhook route ingests messages directly. We expose this hook
    for adapters that support polling (or for tests) so the calling code stays
    uniform.

    TODO: implement once an adapter exists; for webhook providers this can
    stay as ``raise NotImplementedError`` or drain an in-memory queue fed by
    the webhook route.
    """
    raise NotImplementedError
    # The unreachable yield below is required so Python recognises this as an
    # async generator at type-check time.
    yield  # type: ignore[unreachable]
