"""WhatsApp webhook endpoints — wired to the Twilio adapter.

Twilio sends inbound WhatsApp messages as POST form-data. This route parses
them, decides the intent (image verification, code verification, follow-up
question, or general text), runs the appropriate pipeline, and replies via the
Twilio REST API.

No echo detection needed — Twilio only fires webhooks for inbound messages.
"""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings
from app.services.pipeline import verify_code, verify_image
from services.whatsapp import session as session_store
from services.whatsapp.adapters import twilio_wa as twilio_adapter
from services.whatsapp.followup import answer_follow_up
from services.whatsapp.formatter import (
    format_error,
    format_follow_up,
    format_info_only,
    format_verdict,
    format_welcome,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Regex heuristics to classify plain-text messages.
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_CODE_RE = re.compile(r"^[A-Za-z0-9\-/:.]{4,512}$")


@router.get("")
async def verify(request: Request) -> str:
    """Webhook verification handshake (kept for compatibility)."""
    _ = request
    return "ok"


@router.post("")
async def receive(request: Request) -> PlainTextResponse:
    """Inbound Twilio webhook — the main WhatsApp entry point.

    Twilio sends form-data with keys like From, Body, NumMedia, MediaUrl0, etc.
    We parse, branch on content type, and fire processing in the background so
    Twilio gets a fast 200 response (empty TwiML).
    """
    form = await request.form()
    form_data = {k: v for k, v in form.items()}

    logger.info("Twilio webhook: From=%s, Body=%s, NumMedia=%s",
                form_data.get("From"), (form_data.get("Body", "")[:50]), form_data.get("NumMedia"))

    parsed = twilio_adapter.parse_webhook(form_data)
    if parsed is None:
        logger.info("Webhook ignored (invalid payload)")
        return PlainTextResponse("")

    logger.info(
        "Processing message: from=%s, is_image=%s, body=%s, sid=%s",
        parsed.sender_phone, parsed.is_image,
        (parsed.body[:50] if parsed.body else "None"), parsed.message_sid,
    )

    # Fire processing in the background so Twilio gets a quick 200.
    asyncio.create_task(_process_message(parsed))

    # Return empty response — Twilio expects 200 with empty/TwiML body.
    return PlainTextResponse("")


async def _process_message(parsed: twilio_adapter.ParsedWebhook) -> None:
    """Route the inbound message to the right handler and reply."""
    settings = get_settings()
    account_sid = settings.twilio_account_sid or ""
    auth_token = settings.twilio_auth_token or ""
    from_number = settings.twilio_whatsapp_from or ""

    if not account_sid or not auth_token or not from_number:
        logger.error("MISSING CONFIG: twilio_account_sid=%s, twilio_auth_token=%s, twilio_whatsapp_from=%s",
                      bool(account_sid), bool(auth_token), bool(from_number))
        return

    try:
        # --- Route to the right handler ---
        if parsed.is_image:
            logger.info("[%s] ROUTE -> IMAGE (media=%d)", parsed.sender_phone, parsed.num_media)
            reply = await _handle_image(parsed, account_sid=account_sid, auth_token=auth_token)
        elif parsed.body and _URL_RE.match(parsed.body.strip()):
            logger.info("[%s] ROUTE -> URL/CODE (%s)", parsed.sender_phone, parsed.body.strip()[:80])
            reply = await _handle_code(parsed.body.strip(), parsed)
        elif parsed.body and _CODE_RE.match(parsed.body.strip()):
            logger.info("[%s] ROUTE -> CODE (%s)", parsed.sender_phone, parsed.body.strip()[:80])
            reply = await _handle_code(parsed.body.strip(), parsed)
        elif parsed.body and parsed.body.strip():
            logger.info("[%s] ROUTE -> TEXT (%s)", parsed.sender_phone, parsed.body.strip()[:80])
            reply = await _handle_text(parsed.body.strip(), parsed)
        else:
            logger.info("[%s] ROUTE -> WELCOME (empty body)", parsed.sender_phone)
            reply = format_welcome()

        logger.info("[%s] SENDING REPLY (%d chars): %s", parsed.sender_phone, len(reply), reply[:100])
        twilio_adapter.send_message(
            account_sid=account_sid,
            auth_token=auth_token,
            from_number=from_number,
            to_number=parsed.sender_phone,
            body=reply,
        )
        logger.info("[%s] REPLY SENT OK", parsed.sender_phone)
    except Exception:
        logger.exception("[%s] FAILED to process message", parsed.sender_phone)
        try:
            twilio_adapter.send_message(
                account_sid=account_sid,
                auth_token=auth_token,
                from_number=from_number,
                to_number=parsed.sender_phone,
                body=format_error("Something went wrong on our side. Please try again in a moment."),
            )
            logger.info("[%s] ERROR REPLY SENT", parsed.sender_phone)
        except Exception:
            logger.exception("[%s] FAILED to send error reply", parsed.sender_phone)


async def _handle_image(
    parsed: twilio_adapter.ParsedWebhook,
    *,
    account_sid: str,
    auth_token: str,
) -> str:
    """Download the image, run the verification pipeline, store the session."""
    # Pick the first image URL.
    image_url = None
    for url, mime in zip(parsed.media_urls, parsed.media_types):
        if mime.lower().startswith("image/"):
            image_url = url
            break

    if image_url is None:
        logger.warning("[%s] No image found in %d media items", parsed.sender_phone, parsed.num_media)
        return format_error("We couldn't find an image in your message. Please send a photo.")

    logger.info("[%s] Downloading image from Twilio: %s", parsed.sender_phone, image_url)
    image_bytes = await twilio_adapter.download_media(
        image_url,
        account_sid=account_sid,
        auth_token=auth_token,
    )
    logger.info("[%s] Image downloaded: %d bytes", parsed.sender_phone, len(image_bytes))

    logger.info("[%s] Running verify_image pipeline...", parsed.sender_phone)
    verdict_response = await verify_image(image_bytes)
    verdict_dict = verdict_response.model_dump(mode="json")
    logger.info("[%s] Pipeline done: verdict=%s, score=%s",
                parsed.sender_phone, verdict_dict.get("verdict"), verdict_dict.get("score"))

    # Store session for follow-ups.
    ocr_text = verdict_dict.get("ocr", {}).get("text") if verdict_dict.get("ocr") else None
    page_text = verdict_dict.get("page", {}).get("text") if verdict_dict.get("page") else None

    session_store.upsert(
        parsed.sender_phone,
        chat_id=parsed.sender_phone,
        verdict=verdict_dict,
        ocr_text=ocr_text,
        page_text=page_text,
    )
    logger.info("[%s] Session stored for follow-ups", parsed.sender_phone)

    return format_verdict(verdict_dict)


async def _handle_code(code: str, parsed: twilio_adapter.ParsedWebhook) -> str:
    """Run the code/URL verification pipeline."""
    logger.info("[%s] Running verify_code pipeline for: %s", parsed.sender_phone, code[:80])
    verdict_response = await verify_code(code)
    verdict_dict = verdict_response.model_dump(mode="json")
    logger.info("[%s] Code pipeline done: verdict=%s, score=%s",
                parsed.sender_phone, verdict_dict.get("verdict"), verdict_dict.get("score"))

    # Check if this is an info-only result (URL submitted, no image to compare).
    is_info_only = (
        verdict_dict.get("verdict") == "unverifiable"
        and verdict_dict.get("page") is not None
        and bool(verdict_dict.get("page_fields"))
    )

    ocr_text = verdict_dict.get("ocr", {}).get("text") if verdict_dict.get("ocr") else None
    page_text = verdict_dict.get("page", {}).get("text") if verdict_dict.get("page") else None

    session_store.upsert(
        parsed.sender_phone,
        chat_id=parsed.sender_phone,
        verdict=verdict_dict,
        ocr_text=ocr_text,
        page_text=page_text,
    )
    logger.info("[%s] Session stored (info_only=%s)", parsed.sender_phone, is_info_only)

    if is_info_only:
        return format_info_only(verdict_dict)
    return format_verdict(verdict_dict)


async def _handle_text(
    text: str,
    parsed: twilio_adapter.ParsedWebhook,
) -> str:
    """Handle plain text — either a follow-up question or a welcome prompt."""
    settings = get_settings()
    sess = session_store.get(parsed.sender_phone)

    if sess is not None and sess.verdict is not None:
        # User has an active session — treat as a follow-up question.
        logger.info("[%s] FOLLOW-UP: session found, verdict=%s, question=%s",
                    parsed.sender_phone, sess.verdict.get("verdict"), text[:80])
        google_key = settings.google_api_key
        if not google_key:
            logger.warning("[%s] No GOOGLE_API_KEY configured for follow-ups", parsed.sender_phone)
            return format_error(
                "Follow-up questions require a Google API key. "
                "Please ask the admin to configure GOOGLE_API_KEY."
            )
        logger.info("[%s] Calling Gemini for follow-up answer...", parsed.sender_phone)
        answer = await answer_follow_up(
            parsed.sender_phone,
            text,
            api_key=google_key,
            model_name=settings.google_vision_model,
        )
        logger.info("[%s] Gemini answered (%d chars)", parsed.sender_phone, len(answer))
        return format_follow_up(answer)

    # No active session — show welcome message.
    logger.info("[%s] No session found, sending welcome message", parsed.sender_phone)
    return format_welcome()
