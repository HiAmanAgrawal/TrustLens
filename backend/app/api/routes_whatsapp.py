"""WhatsApp webhook endpoints.

Two routes live here because Meta Cloud requires a GET handshake to verify the
webhook URL, while POST carries the actual message events. Twilio uses POST
only — the GET route is harmless for both.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
async def verify(request: Request) -> str:
    """Webhook verification handshake (Meta Cloud API).

    Meta sends ``hub.mode``, ``hub.verify_token`` and ``hub.challenge`` as
    query params. We echo the challenge back if the token matches.

    TODO: read ``META_WABA_VERIFY_TOKEN`` from settings and compare.
    """
    _ = request
    return "ok"


@router.post("")
async def receive(request: Request) -> dict:
    """Inbound message webhook.

    A single user can verify a product in two ways from WhatsApp:
      - send a photo of the pack -> image pipeline
      - send the typed barcode/QR number -> code-text pipeline

    This route inspects the parsed message, decides which path it belongs to,
    and dispatches accordingly. Both paths end at ``services.matcher.engine.match``.

    TODO:
      1. Parse the payload — shape depends on the chosen provider, so dispatch
         through ``services.whatsapp`` rather than parsing here.
      2. Branch on the message type:
         - has media -> download (Twilio: signed URL + basic auth, Meta: GET
           /media via Graph API), then run the same pipeline as ``routes_images``.
         - text only -> normalise the text (strip spaces, extract batch param
           if it's a URL) and run the same pipeline as ``routes_codes``.
         - text that doesn't look like a code -> reply with a short usage hint
           ("Send a photo of the pack OR type the barcode number").
      3. Reply via ``services.whatsapp.send_receive.send_message``.
    """
    _ = request
    return {"status": "not_implemented"}
