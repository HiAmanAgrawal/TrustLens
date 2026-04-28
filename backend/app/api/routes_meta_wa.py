"""Meta WhatsApp Cloud API webhook endpoint.

Mounted at /webhook/whatsapp/meta

  GET  /webhook/whatsapp/meta  — webhook verification challenge (Meta requires this
                                  once when you register the webhook URL in your app).
  POST /webhook/whatsapp/meta  — inbound messages from users.

All message processing is delegated to _process_message() in routes_whatsapp.py
so the business logic lives in exactly one place regardless of provider.

SETUP:
  1. Set in .env:
       META_WABA_PHONE_ID=<your phone number ID from Meta>
       META_WABA_TOKEN=<permanent system user access token>
       META_WABA_VERIFY_TOKEN=<any secret string — put the same value in your Meta app>
  2. In the Meta App dashboard → WhatsApp → Configuration:
       Webhook URL:  https://<your-domain>/webhook/whatsapp/meta
       Verify Token: <META_WABA_VERIFY_TOKEN>
       Subscribed fields: messages
  3. Use ngrok or a public URL for local testing:
       ngrok http 8000
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# GET — webhook verification (called once by Meta during setup)
# ---------------------------------------------------------------------------

@router.get("")
async def verify(request: Request) -> PlainTextResponse:
    """Respond to Meta's webhook verification challenge."""
    settings = get_settings()
    verify_token = settings.meta_waba_verify_token or ""

    from services.whatsapp.adapters.meta_wa import verify_webhook
    params = dict(request.query_params)
    challenge = verify_webhook(params, verify_token=verify_token)

    if challenge:
        return PlainTextResponse(challenge, status_code=200)

    logger.warning("meta_wa.verify | invalid verify_token or mode")
    return PlainTextResponse("Forbidden", status_code=403)


# ---------------------------------------------------------------------------
# POST — inbound messages
# ---------------------------------------------------------------------------

@router.post("")
async def receive(request: Request) -> PlainTextResponse:
    """Receive an inbound WhatsApp message from Meta and process it.

    Meta expects a fast 200 response — all work is done in a background task.
    """
    import asyncio

    try:
        payload = await request.json()
    except Exception:
        logger.warning("meta_wa.receive | failed to parse JSON body")
        return PlainTextResponse("", status_code=200)

    logger.info("meta_wa.receive | payload object=%s", payload.get("object"))

    # Meta sends a test ping with object="whatsapp_business_account" but no messages
    if payload.get("object") != "whatsapp_business_account":
        return PlainTextResponse("", status_code=200)

    from services.whatsapp.adapters.meta_wa import parse_webhook
    messages = parse_webhook(payload)

    for msg in messages:
        asyncio.create_task(_process_meta_message(msg))

    return PlainTextResponse("", status_code=200)


# ---------------------------------------------------------------------------
# Message processor (mirrors _process_message in routes_whatsapp.py)
# ---------------------------------------------------------------------------

async def _process_meta_message(parsed: "ParsedWebhook") -> None:  # type: ignore[name-defined]
    """Route a parsed Meta message through the same pipeline as Twilio messages."""
    from services.whatsapp.adapters.meta_wa import ParsedWebhook, download_media, send_message

    settings = get_settings()
    phone_id    = settings.meta_waba_phone_id or ""
    token       = settings.meta_waba_token or ""

    if not phone_id or not token:
        logger.error("meta_wa._process | META_WABA_PHONE_ID or META_WABA_TOKEN not set")
        return

    try:
        from app.core.rephraser import detect_user_language, rephrase as rephrase_reply
        user_lang = detect_user_language(parsed.body or "")

        # Route to the appropriate handler — same logic as Twilio
        if parsed.is_image:
            logger.info("[%s] ROUTE -> IMAGE", parsed.sender_phone)
            reply = await _handle_image_meta(parsed, token=token)
        elif parsed.body and parsed.body.strip():
            logger.info("[%s] ROUTE -> TEXT (%s)", parsed.sender_phone, (parsed.body or "")[:80])
            # Reuse the Twilio handler (it only uses parsed.sender_phone + body)
            from app.api.routes_whatsapp import _handle_text
            reply = await _handle_text(parsed.body.strip(), parsed)
        else:
            from services.whatsapp.formatter import format_welcome
            reply = format_welcome()

        # Rephrase to Hinglish / Hindi if needed
        if user_lang != "en" and reply:
            reply = await rephrase_reply(reply, user_lang, user_message=parsed.body or "")

        logger.info("[%s] SENDING META REPLY (%d chars)", parsed.sender_phone, len(reply))
        send_message(
            phone_number_id=phone_id,
            access_token=token,
            to_number=parsed.sender_phone,
            body=reply,
        )
        logger.info("[%s] META REPLY SENT", parsed.sender_phone)

    except Exception:
        logger.exception("[%s] Failed to process Meta message", parsed.sender_phone)
        try:
            from services.whatsapp.formatter import format_error
            send_message(
                phone_number_id=phone_id,
                access_token=token,
                to_number=parsed.sender_phone,
                body=format_error("Something went wrong on our side. Please try again."),
            )
        except Exception:
            logger.exception("[%s] Failed to send Meta error reply", parsed.sender_phone)


async def _handle_image_meta(parsed: "ParsedWebhook", *, token: str) -> str:  # type: ignore[name-defined]
    """Download the image via Meta media API then run the unified scan pipeline."""
    from services.whatsapp.adapters.meta_wa import download_media

    if not parsed.media_urls:
        from services.whatsapp.formatter import format_error
        return format_error("No image found in your message. Please send a photo.")

    media_id = parsed.media_urls[0]
    logger.info("[%s] Downloading Meta media id=%s", parsed.sender_phone, media_id)
    image_bytes = await download_media(media_id, access_token=token)
    logger.info("[%s] Downloaded %d bytes", parsed.sender_phone, len(image_bytes))

    session_id = parsed.sender_phone

    try:
        from app.core.database import get_session_factory
        from app.services.pipeline_service import run_unified_scan
        from app.services.product_context import (
            build_context_from_grocery_response,
            build_context_from_medicine_response,
            store_product_context,
        )
        from services.whatsapp.formatter import (
            format_grocery_scan,
            format_medicine_scan,
            format_prescription_scan,
        )

        factory = get_session_factory()
        async with factory() as db:
            try:
                result = await run_unified_scan(db, image_bytes=image_bytes, user_id=None, lang="en")
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        if result.grocery:
            ctx = build_context_from_grocery_response(result.grocery, session_id)
            await store_product_context(session_id, ctx)
            return format_grocery_scan(result.grocery)
        if result.medicine:
            ctx = build_context_from_medicine_response(result.medicine, session_id)
            await store_product_context(session_id, ctx)
            return format_medicine_scan(result.medicine)
        if result.prescription:
            return format_prescription_scan(result.prescription)

    except Exception:
        logger.exception("[%s] Meta image scan failed", parsed.sender_phone)

    # Legacy fallback
    from app.services.pipeline import verify_image
    from services.whatsapp.formatter import format_verdict
    verdict_response = await verify_image(image_bytes)
    return format_verdict(verdict_response.model_dump(mode="json"))
