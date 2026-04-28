"""Meta WhatsApp Cloud API adapter.

Handles all communication with the official Meta WhatsApp Business Cloud API
(aka the Graph API for WhatsApp). No Twilio, no sandbox, no join phrases.

FREE TIER:
  1 000 user-initiated conversations / month forever (as of Meta's 2024 pricing).
  Service-initiated (business-initiated) messages also have a free allowance.

SETUP SUMMARY (see docs/ for full walkthrough):
  1. Create a Meta App at developers.facebook.com → WhatsApp product.
  2. Add a WhatsApp Business Account (WABA) and a phone number.
  3. Copy Phone Number ID  → META_WABA_PHONE_ID
  4. Generate a permanent System User token → META_WABA_TOKEN
  5. Set any string as META_WABA_VERIFY_TOKEN (used for webhook challenge).
  6. Register your /webhook/whatsapp/meta endpoint in the Meta App dashboard.
  7. Subscribe to the "messages" webhook field.

WEBHOOK FORMAT (inbound):
  POST JSON with nested "entry" → "changes" → "value" → "messages" array.
  Media messages carry a media_id (not a direct URL); a separate Graph API
  call converts the ID into a short-lived download URL.

SENDING:
  POST https://graph.facebook.com/v20.0/{phone_number_id}/messages
  Authorization: Bearer {access_token}
  Body: JSON with messaging_product, to, type, text.body

PHONE NUMBER FORMAT:
  Meta sends/receives numbers without the "whatsapp:" prefix but we normalise
  to "whatsapp:+E164" internally so sessions are keyed the same way as Twilio.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_GRAPH_URL = "https://graph.facebook.com/v20.0"

_http_client: httpx.AsyncClient | None = None


def _get_http() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


# ---------------------------------------------------------------------------
# Shared ParsedWebhook — same shape as twilio_wa so _process_message is reused
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParsedWebhook:
    sender_phone: str           # normalised: "whatsapp:+919876543210"
    sender_name: str | None
    body: str | None
    num_media: int
    media_urls: list[str] = field(default_factory=list)    # resolved download URLs
    media_types: list[str] = field(default_factory=list)
    is_image: bool = False
    message_sid: str = ""       # wamid from Meta


# ---------------------------------------------------------------------------
# Webhook verification (GET — Meta sends hub.challenge to confirm the endpoint)
# ---------------------------------------------------------------------------

def verify_webhook(
    params: dict[str, str],
    *,
    verify_token: str,
) -> str | None:
    """Return the hub.challenge string if the token matches, else None."""
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == verify_token:
        logger.info("meta_wa.verify_webhook | challenge accepted")
        return challenge

    logger.warning(
        "meta_wa.verify_webhook | FAILED — mode=%r token_match=%s",
        mode, token == verify_token,
    )
    return None


# ---------------------------------------------------------------------------
# Inbound webhook parsing (POST — actual messages)
# ---------------------------------------------------------------------------

def parse_webhook(payload: dict[str, Any]) -> list[ParsedWebhook]:
    """Convert a Meta webhook JSON payload into a list of ParsedWebhook objects.

    A single POST may carry multiple message events (batching). Returns one
    ParsedWebhook per message so the caller can process them individually.
    Returns an empty list for non-message events (status updates, etc.).
    """
    results: list[ParsedWebhook] = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            value = change.get("value", {})
            messages = value.get("messages", [])
            contacts = {c["wa_id"]: c.get("profile", {}).get("name") for c in value.get("contacts", [])}

            for msg in messages:
                sender_raw = msg.get("from", "")
                # Normalise to "whatsapp:+E164" so session keys are uniform
                sender = _normalise_number(sender_raw)
                name   = contacts.get(sender_raw)
                wamid  = msg.get("id", "")
                mtype  = msg.get("type", "text")

                if mtype == "text":
                    body = msg.get("text", {}).get("body")
                    results.append(ParsedWebhook(
                        sender_phone=sender,
                        sender_name=name,
                        body=body,
                        num_media=0,
                        message_sid=wamid,
                    ))

                elif mtype == "image":
                    img = msg.get("image", {})
                    media_id   = img.get("id", "")
                    mime_type  = img.get("mime_type", "image/jpeg")
                    caption    = img.get("caption")
                    results.append(ParsedWebhook(
                        sender_phone=sender,
                        sender_name=name,
                        body=caption,
                        num_media=1,
                        media_urls=[media_id],   # ID — resolved later by download_media()
                        media_types=[mime_type],
                        is_image=True,
                        message_sid=wamid,
                    ))

                elif mtype == "document":
                    doc       = msg.get("document", {})
                    media_id  = doc.get("id", "")
                    mime_type = doc.get("mime_type", "application/octet-stream")
                    caption   = doc.get("caption")
                    is_image  = mime_type.startswith("image/") or mime_type == "application/octet-stream"
                    results.append(ParsedWebhook(
                        sender_phone=sender,
                        sender_name=name,
                        body=caption,
                        num_media=1,
                        media_urls=[media_id],
                        media_types=[mime_type],
                        is_image=is_image,
                        message_sid=wamid,
                    ))

                else:
                    logger.info("meta_wa.parse_webhook | unsupported type=%s from=%s", mtype, sender)

    logger.info("meta_wa.parse_webhook | extracted %d messages", len(results))
    return results


# ---------------------------------------------------------------------------
# Media download — two-step: resolve media ID → URL → download bytes
# ---------------------------------------------------------------------------

async def download_media(
    media_id: str,
    *,
    access_token: str,
) -> bytes:
    """Download media bytes using a Meta media ID.

    Step 1: GET /v20.0/{media_id} → {"url": "...", "mime_type": "..."}
    Step 2: GET the resolved URL with Bearer auth.
    """
    client = _get_http()
    headers = {"Authorization": f"Bearer {access_token}"}

    # Step 1 — resolve ID to URL
    meta_resp = await client.get(
        f"{_GRAPH_URL}/{media_id}",
        headers=headers,
    )
    meta_resp.raise_for_status()
    resolved_url = meta_resp.json().get("url")
    if not resolved_url:
        raise ValueError(f"Meta media API returned no URL for id={media_id!r}")

    logger.info("meta_wa.download_media | id=%s resolved_url=%s...", media_id, resolved_url[:60])

    # Step 2 — download bytes
    dl_resp = await client.get(resolved_url, headers=headers, follow_redirects=True)
    dl_resp.raise_for_status()
    logger.info("meta_wa.download_media | downloaded %d bytes", len(dl_resp.content))
    return dl_resp.content


# ---------------------------------------------------------------------------
# Sending messages
# ---------------------------------------------------------------------------

def send_message(
    *,
    phone_number_id: str,
    access_token: str,
    to_number: str,
    body: str,
) -> str:
    """Send a WhatsApp text message via the Meta Cloud API (synchronous).

    ``to_number`` may have the "whatsapp:" prefix — it is stripped automatically.
    Returns the wamid of the sent message.
    """
    to_clean = to_number.replace("whatsapp:", "").lstrip("+")
    logger.info("meta_wa.send_message | to=%s chars=%d", to_clean, len(body))

    import httpx as _httpx
    resp = _httpx.post(
        f"{_GRAPH_URL}/{phone_number_id}/messages",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "to": to_clean,
            "type": "text",
            "text": {"body": body, "preview_url": False},
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    data   = resp.json()
    wamid  = data.get("messages", [{}])[0].get("id", "unknown")
    logger.info("meta_wa.send_message | sent wamid=%s", wamid)
    return wamid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_number(raw: str) -> str:
    """Convert a Meta phone number (e.g. '919876543210') to 'whatsapp:+919876543210'."""
    number = raw.lstrip("+")
    return f"whatsapp:+{number}"


async def close() -> None:
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None
