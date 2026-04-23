"""Gemini-powered follow-up Q&A for WhatsApp conversations.

After a user receives a verification verdict, they can ask natural-language
follow-up questions like "Is this safe for children?" or "What are the side
effects?".  This module builds a Gemini prompt that includes the verification
context and returns a concise, WhatsApp-friendly plain-text answer.

Uses ``google-genai`` (already a project dependency) with ``GOOGLE_API_KEY``.
"""

from __future__ import annotations

import logging
from typing import Any

from google import genai

from services.whatsapp import session as session_store

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are TrustLens, a medicine verification assistant on WhatsApp.

You have just verified a medicine for the user.  The verification data is
provided below.  Answer the user's follow-up question based ONLY on this
data and your general pharmaceutical knowledge.

Rules:
- Be concise — WhatsApp messages should be short and scannable.
- Use plain text only (no markdown headers, no triple-backtick code blocks).
- Use *bold* sparingly for emphasis (WhatsApp supports it).
- If you genuinely don't know, say so — never invent drug-specific facts.
- Always end with a brief reminder that you are an AI assistant, not a doctor.
"""


def _build_context(sess: session_store.Session) -> str:
    """Serialise the session's verdict into a text block for the LLM."""
    v = sess.verdict or {}
    parts: list[str] = []

    parts.append(f"Verdict: {v.get('verdict', 'unknown')} (score {v.get('score', 'N/A')}/10)")
    parts.append(f"Summary: {v.get('summary', 'N/A')}")

    label_fields = v.get("label_fields", {})
    if label_fields:
        parts.append("Label fields (from the medicine pack):")
        for k, val in label_fields.items():
            parts.append(f"  {k}: {val}")

    page_fields = v.get("page_fields", {})
    if page_fields:
        parts.append("Manufacturer page fields:")
        for k, val in page_fields.items():
            parts.append(f"  {k}: {val}")

    evidence = v.get("evidence", [])
    if evidence:
        parts.append("Evidence (field comparisons):")
        for e in evidence:
            parts.append(f"  {e}")

    if sess.ocr_text:
        parts.append(f"OCR text from label:\n{sess.ocr_text[:1000]}")

    if sess.page_text:
        parts.append(f"Manufacturer page text:\n{sess.page_text[:1000]}")

    return "\n".join(parts)


def _build_messages(
    sess: session_store.Session, question: str
) -> list[dict[str, str]]:
    """Build the Gemini message list including conversation history."""
    messages: list[dict[str, str]] = []

    # Context message.
    context = _build_context(sess)
    messages.append({"role": "user", "parts": [f"[Verification Data]\n{context}"]})
    messages.append({"role": "model", "parts": ["Understood. I have the verification data. Ask me anything about this medicine."]})

    # Replay prior follow-ups so the conversation is multi-turn.
    for turn in sess.follow_ups:
        role = "user" if turn["role"] == "user" else "model"
        messages.append({"role": role, "parts": [turn["content"]]})

    # Current question.
    messages.append({"role": "user", "parts": [question]})
    return messages


async def answer_follow_up(
    phone: str,
    question: str,
    *,
    api_key: str,
    model_name: str = "gemini-2.5-flash",
) -> str:
    """Generate a follow-up answer using Gemini.

    Returns a plain-text string suitable for sending as a WhatsApp message.
    Falls back to a canned response if the API call fails.
    """
    sess = session_store.get(phone)
    if sess is None or sess.verdict is None:
        return (
            "I don't have a recent verification to reference. "
            "Please send a photo of your medicine pack first, then ask your question!\n\n"
            "Send a photo to get started."
        )

    try:
        client = genai.Client(api_key=api_key)
        messages = _build_messages(sess, question)

        logger.info("[%s] Follow-up: sending %d messages to Gemini (%s)", phone, len(messages), model_name)
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=messages,
            config=genai.types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                temperature=0.3,
                max_output_tokens=500,
            ),
        )

        answer = response.text.strip() if response.text else "I wasn't able to generate an answer. Please try again."
        logger.info("[%s] Follow-up: Gemini answered (%d chars)", phone, len(answer))

        # Persist the exchange in session history.
        session_store.add_follow_up(phone, "user", question)
        session_store.add_follow_up(phone, "assistant", answer)

        return answer

    except Exception:
        logger.exception("Gemini follow-up call failed for %s", phone)
        return (
            "Sorry, I couldn't process your question right now. "
            "Please try again in a moment, or send a new photo to verify another medicine."
        )
