"""WhatsApp webhook endpoints — wired to the Twilio adapter.

Twilio sends inbound WhatsApp messages as POST form-data. This route parses
them, decides the intent (image scan, code verification, product follow-up,
onboarding, or greeting), runs the appropriate pipeline, and replies via the
Twilio REST API.

MESSAGE ROUTING (in priority order):
  1. Image         → Phase 3 unified scan (grocery / medicine / prescription)
                     → product context stored in Redis for follow-ups
                     → falls back to legacy verify_image if Phase 3 errors
  2. URL / barcode → legacy verify_code pipeline (medicine barcode check)
  3. Text, Phase 3 product context active → LangGraph product advisor (with tools)
  4. Text, legacy scan session active     → Gemini follow-up (medicine Q&A)
  5. Text, no session                     → LangGraph conversation agent
                                            (onboarding / personalised greeting)

No echo detection needed — Twilio only fires webhooks for inbound messages.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings
from app.models.enums import MessageDirectionEnum
from app.services.pipeline import verify_code, verify_image
from services.whatsapp import session as session_store
from services.whatsapp.adapters import twilio_wa as twilio_adapter
from services.whatsapp.followup import answer_follow_up
from services.whatsapp.formatter import (
    format_advisor_reply,
    format_error,
    format_follow_up,
    format_grocery_scan,
    format_info_only,
    format_medicine_scan,
    format_prescription_scan,
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
    """
    Download the image, run the Phase 3 unified pipeline, store product context.

    Phase 3 pipeline classifies the image as grocery / medicine / prescription,
    stores a rich product context in Redis (2-hour TTL) for follow-up Q&A via
    the LangGraph product advisor, and returns a formatted WhatsApp message.

    Falls back to the legacy verify_image pipeline if Phase 3 raises an
    unrecoverable error, so existing medicine-barcode users are never blocked.
    """
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

    # ── Phase 3 unified scan ─────────────────────────────────────────────────
    # Use the sender's WhatsApp ID as the session key so follow-up text
    # messages in the same chat automatically reach the product advisor.
    session_id = parsed.sender_phone

    try:
        from app.core.database import get_session_factory
        from app.services.pipeline_service import run_unified_scan
        from app.services.product_context import (
            build_context_from_grocery_response,
            build_context_from_medicine_response,
            store_product_context,
        )

        logger.info("[%s] Running Phase 3 unified scan...", parsed.sender_phone)
        factory = get_session_factory()
        async with factory() as db:
            try:
                result = await run_unified_scan(
                    db,
                    image_bytes=image_bytes,
                    user_id=None,
                    lang="en",
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        logger.info(
            "[%s] Phase 3 scan done — grocery=%s medicine=%s prescription=%s",
            parsed.sender_phone,
            result.grocery is not None,
            result.medicine is not None,
            result.prescription is not None,
        )

        # Store product context and format reply based on detected type.
        if result.grocery:
            ctx = build_context_from_grocery_response(result.grocery, session_id)
            await store_product_context(session_id, ctx)
            logger.info("[%s] Grocery context stored (session_id=%r)", parsed.sender_phone, session_id)
            return format_grocery_scan(result.grocery)

        if result.medicine:
            ctx = build_context_from_medicine_response(result.medicine, session_id)
            await store_product_context(session_id, ctx)
            logger.info("[%s] Medicine context stored (session_id=%r)", parsed.sender_phone, session_id)
            return format_medicine_scan(result.medicine)

        if result.prescription:
            # Prescriptions are read-only — no product context needed for Q&A.
            logger.info("[%s] Prescription scan done (no context stored)", parsed.sender_phone)
            return format_prescription_scan(result.prescription)

        # Phase 3 couldn't classify — fall through to legacy pipeline below.
        logger.warning("[%s] Phase 3 returned no classified result; trying legacy pipeline", parsed.sender_phone)

    except Exception:
        logger.exception(
            "[%s] Phase 3 unified scan failed — falling back to legacy verify_image",
            parsed.sender_phone,
        )

    # ── Legacy fallback (medicine barcode verification) ──────────────────────
    logger.info("[%s] Running legacy verify_image pipeline...", parsed.sender_phone)
    verdict_response = await verify_image(image_bytes)
    verdict_dict = verdict_response.model_dump(mode="json")
    logger.info("[%s] Legacy pipeline done: verdict=%s score=%s",
                parsed.sender_phone, verdict_dict.get("verdict"), verdict_dict.get("score"))

    ocr_text  = verdict_dict.get("ocr", {}).get("text")  if verdict_dict.get("ocr")  else None
    page_text = verdict_dict.get("page", {}).get("text") if verdict_dict.get("page") else None
    session_store.upsert(
        parsed.sender_phone,
        chat_id=parsed.sender_phone,
        verdict=verdict_dict,
        ocr_text=ocr_text,
        page_text=page_text,
    )
    logger.info("[%s] Legacy session stored for follow-ups", parsed.sender_phone)
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
    """
    Handle plain-text messages.

    Priority:
      1. Phase 3 product context active (Redis) → LangGraph product advisor
         with tools (web search, health check, trust scoring, DB lookup).
      2. Legacy scan session active (in-memory) → Gemini medicine Q&A.
      3. No scan session → LangGraph conversation agent
         (onboarding / personalised greeting).
      4. Agent failure → static welcome fallback.

    The Phase 3 path covers all products scanned via the unified pipeline
    (grocery, medicine, prescription). The legacy path covers scans done via
    the old verify_image / verify_code pipelines or if Phase 3 fell back.
    """
    settings = get_settings()

    # ── Priority 1: Phase 3 product context → product advisor ────────────────
    try:
        from app.services.product_context import get_product_context
        from app.agents.product_advisor.graph import run_product_advisor

        product_ctx = await get_product_context(parsed.sender_phone)
        if product_ctx:
            logger.info(
                "[%s] PRODUCT-ADVISOR: context found (scan_type=%r brand=%r), question=%r",
                parsed.sender_phone,
                product_ctx.get("scan_type"),
                product_ctx.get("brand_name"),
                text[:80],
            )
            result = await run_product_advisor(
                text,
                product_context=product_ctx,
                session_id=parsed.sender_phone,
            )
            logger.info(
                "[%s] PRODUCT-ADVISOR: done tools=%s answer_chars=%d error=%r",
                parsed.sender_phone,
                result.get("tools_called"),
                len(result.get("answer") or ""),
                result.get("error"),
            )
            return format_advisor_reply(
                result.get("answer") or "I wasn't able to generate an answer. Please try again.",
                result.get("tools_called"),
            )
    except Exception:
        logger.exception(
            "[%s] Product advisor failed — falling through to legacy or agent",
            parsed.sender_phone,
        )

    # ── Priority 2: Legacy scan session → Gemini medicine Q&A ───────────────
    sess = session_store.get(parsed.sender_phone)
    if sess is not None and sess.verdict is not None:
        logger.info(
            "[%s] LEGACY-FOLLOWUP: session found verdict=%r question=%r",
            parsed.sender_phone, sess.verdict.get("verdict"), text[:80],
        )
        google_key = settings.google_api_key
        if not google_key:
            logger.warning("[%s] No GOOGLE_API_KEY — cannot answer follow-up", parsed.sender_phone)
            return format_error(
                "Follow-up questions need a Google API key. "
                "Please ask the admin to configure GOOGLE_API_KEY."
            )
        answer = await answer_follow_up(
            parsed.sender_phone,
            text,
            api_key=google_key,
            model_name=settings.google_vision_model,
        )
        logger.info("[%s] Gemini follow-up answered (%d chars)", parsed.sender_phone, len(answer))
        return format_follow_up(answer)

    # ── Priority 3: Conversational agent (onboarding / greeting) ────────────
    logger.info("[%s] No scan context; routing to conversation agent", parsed.sender_phone)
    try:
        reply = await _run_agent(
            wa_id=parsed.sender_phone,
            phone_number=parsed.sender_phone.replace("whatsapp:", ""),
            text=text,
        )
        if reply:
            return reply
    except Exception:
        logger.exception("[%s] Conversation agent failed — sending welcome fallback", parsed.sender_phone)

    return format_welcome()


# ---------------------------------------------------------------------------
# LangGraph agent runner
# ---------------------------------------------------------------------------

async def _run_agent(*, wa_id: str, phone_number: str, text: str | None) -> str:
    """
    Invoke the conversational agent for a single inbound text message.

    Manages its own DB session so the agent graph nodes can access the DB
    without being tied to the FastAPI request lifecycle (this runs in a
    background task).

    Saves both the inbound message and the agent reply to conversation_messages
    so the greeting node has accurate windowed context on the next turn.
    """
    from app.agents import conversation_graph
    from app.core.database import get_session_factory
    from app.services.message_service import save_message

    factory = get_session_factory()
    async with factory() as session:
        try:
            # Persist the inbound message before running the graph so the
            # greeting node's windowed context includes the current message.
            await save_message(
                session,
                whatsapp_user_id=wa_id,
                direction=MessageDirectionEnum.INBOUND,
                message_text=text,
            )

            initial_state = {
                "whatsapp_user_id": wa_id,
                "phone_number": phone_number,
                "incoming_text": text,
                "incoming_media_url": None,
                "incoming_media_type": None,
                "lang": "en",          # default; script detection can be added later
                "is_new_user": False,  # router_node overwrites this
                "onboarding_step": None,
                "db_user_id": None,
                "db_user_name": None,
                "db_user_diet": None,
                "session_data": None,
                "response_text": "",
                "response_sent": False,
            }
            config = {"configurable": {"db_session": session}}

            logger.info("agent.invoke.start | wa_id=%r text=%r", wa_id, (text or "")[:60])
            result = await conversation_graph.ainvoke(initial_state, config=config)
            reply: str = result.get("response_text") or ""
            logger.info("agent.invoke.done | wa_id=%r reply_chars=%d", wa_id, len(reply))

            # Persist the outbound reply for future context windows.
            if reply:
                await save_message(
                    session,
                    whatsapp_user_id=wa_id,
                    direction=MessageDirectionEnum.OUTBOUND,
                    message_text=reply,
                )

            await session.commit()
            return reply

        except Exception:
            await session.rollback()
            raise
