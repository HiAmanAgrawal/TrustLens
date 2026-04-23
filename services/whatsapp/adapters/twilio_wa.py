"""Twilio WhatsApp adapter.

Handles all communication with the Twilio WhatsApp Sandbox / Business API:
- Parsing inbound webhook payloads (form-data from Twilio)
- Downloading media attachments (images sent by users)
- Sending text replies back via the Twilio REST API

Uses the ``twilio`` SDK for sending and ``httpx`` for media downloads.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from twilio.rest import Client as TwilioClient

logger = logging.getLogger(__name__)

# Lazy-initialised Twilio client and httpx client.
_twilio_client: TwilioClient | None = None
_http_client: httpx.AsyncClient | None = None


def _get_twilio_client(account_sid: str, auth_token: str) -> TwilioClient:
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = TwilioClient(account_sid, auth_token)
    return _twilio_client


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


@dataclass(frozen=True)
class ParsedWebhook:
    """Everything we need from an inbound Twilio webhook."""

    sender_phone: str          # E.164 format, e.g. "whatsapp:+919876543210"
    sender_name: str | None
    body: str | None           # text content; None for media-only messages
    num_media: int             # number of media attachments
    media_urls: list[str] = field(default_factory=list)     # direct-download URLs (need Basic auth)
    media_types: list[str] = field(default_factory=list)    # MIME types
    is_image: bool = False     # True if at least one attachment is an image
    message_sid: str = ""      # Twilio message SID


def parse_webhook(form_data: dict[str, str]) -> ParsedWebhook | None:
    """Convert Twilio webhook form-data into a ``ParsedWebhook``.

    Twilio sends inbound WhatsApp messages as POST form-data with keys like:
    ``From``, ``To``, ``Body``, ``NumMedia``, ``MediaUrl0``, ``MediaContentType0``, etc.

    Returns ``None`` only if the payload is clearly not a valid message.
    Twilio NEVER sends echoes of outbound messages as webhooks — no echo
    detection needed.
    """
    sender = form_data.get("From", "")
    if not sender:
        logger.warning("Webhook missing 'From' field, ignoring")
        return None

    body = form_data.get("Body") or None
    num_media = int(form_data.get("NumMedia", "0"))

    media_urls: list[str] = []
    media_types: list[str] = []
    image_types = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic", "image/heif"}
    # When sent as a Document, WhatsApp delivers image files as
    # application/octet-stream — treat those as images too.
    doc_image_types = {"application/octet-stream"}
    is_image = False

    for i in range(num_media):
        url = form_data.get(f"MediaUrl{i}", "")
        mime = form_data.get(f"MediaContentType{i}", "").lower()
        if url:
            media_urls.append(url)
            media_types.append(mime)
            if mime in image_types or mime in doc_image_types:
                is_image = True

    logger.info(
        "Parsed Twilio webhook: from=%s, body=%s, num_media=%d, is_image=%s",
        sender, (body[:50] if body else "None"), num_media, is_image,
    )

    return ParsedWebhook(
        sender_phone=sender,
        sender_name=form_data.get("ProfileName"),
        body=body,
        num_media=num_media,
        media_urls=media_urls,
        media_types=media_types,
        is_image=is_image,
        message_sid=form_data.get("MessageSid", ""),
    )


async def download_media(
    url: str,
    *,
    account_sid: str,
    auth_token: str,
) -> bytes:
    """Download media bytes from a Twilio media URL.

    Twilio media URLs require HTTP Basic auth with account SID + auth token.
    """
    logger.info("Downloading Twilio media: %s", url)
    client = _get_http_client()
    resp = await client.get(
        url,
        auth=(account_sid, auth_token),
        follow_redirects=True,
    )
    resp.raise_for_status()
    logger.info("Media downloaded: %d bytes, status=%d", len(resp.content), resp.status_code)
    return resp.content


def send_message(
    *,
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
    body: str,
) -> str:
    """Send a WhatsApp message via Twilio REST API.

    Returns the message SID of the sent message.
    ``from_number`` and ``to_number`` should include the ``whatsapp:`` prefix,
    e.g. ``whatsapp:+14155238886``.
    """
    logger.info("Sending Twilio message: to=%s (%d chars)", to_number, len(body))
    client = _get_twilio_client(account_sid, auth_token)
    message = client.messages.create(
        from_=from_number,
        to=to_number,
        body=body,
    )
    logger.info("Message sent: sid=%s, status=%s", message.sid, message.status)
    return message.sid


async def close() -> None:
    """Shut down the shared HTTP client (call on app shutdown)."""
    global _http_client, _twilio_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None
    _twilio_client = None
