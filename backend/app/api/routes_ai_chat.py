"""AI chat endpoint — POST /api/ai/chat.

Accepts a conversation history and optional scan context, forwards to
Google Gemini if an API key is configured, otherwise returns a canned
response so the app degrades gracefully without credentials.

Request body (from Flutter ChatMessage.toJson):
    {
        "messages": [{"role": "user"|"assistant", "content": "..."}],
        "scan_context": {"product": ..., "verdict": ..., ...} | null,
        "user_id": "..." | null
    }

Response body (matches Flutter ChatResponse.fromJson):
    {
        "reply": "...",
        "suggestions": ["...", "..."]
    }
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class _Message(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[_Message]
    scan_context: dict[str, Any] | None = None
    user_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    suggestions: list[str] = []


# ---------------------------------------------------------------------------
# Canned fallback (no API key)
# ---------------------------------------------------------------------------

_CANNED_SUGGESTIONS = [
    "Tell me more",
    "Is this safe for me?",
    "What should I do next?",
]


def _canned_response(req: ChatRequest) -> ChatResponse:
    last = req.messages[-1].content if req.messages else ""
    reply = (
        "I'm here to help with health and product safety questions. "
        "My AI features require a Google API key to be configured on the server. "
        "Please ask your administrator to set the GOOGLE_API_KEY environment variable.\n\n"
        f"Your question was: \"{last}\"\n\n"
        "\u26A0 This is not medical advice. Consult a qualified healthcare provider."
    )
    return ChatResponse(reply=reply, suggestions=_CANNED_SUGGESTIONS)


# ---------------------------------------------------------------------------
# Gemini chat
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are TrustLens AI, a helpful health and product safety assistant. "
    "You help users understand medicine labels, food ingredients, and product authenticity. "
    "Always be accurate, empathetic, and concise. "
    "End every response with a brief disclaimer: "
    "'⚠ This is not medical advice. Consult a qualified healthcare provider for medical decisions.' "
    "Keep responses under 300 words. "
    "Suggest 2-3 short follow-up questions at the end as a JSON array in this exact format: "
    'SUGGESTIONS:["question 1","question 2","question 3"]'
)


async def _gemini_chat(api_key: str, req: ChatRequest) -> ChatResponse:
    import json
    import re

    import google.generativeai as genai  # type: ignore

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    # Build conversation history for Gemini
    history = []
    for msg in req.messages[:-1]:  # all but the last (which is the new user message)
        history.append({
            "role": "user" if msg.role == "user" else "model",
            "parts": [msg.content],
        })

    # Inject scan context into system prompt if available
    system = _SYSTEM_PROMPT
    if req.scan_context:
        ctx_lines = "\n".join(f"  {k}: {v}" for k, v in req.scan_context.items())
        system += f"\n\nCurrent scan context:\n{ctx_lines}"

    chat = model.start_chat(history=history)

    # Prepend system context to first message if no history yet
    last_content = req.messages[-1].content if req.messages else ""
    if not history:
        last_content = f"{system}\n\nUser: {last_content}"

    response = await chat.send_message_async(last_content)
    full_text: str = response.text

    # Extract suggestions from the SUGGESTIONS:[...] marker
    suggestions: list[str] = []
    match = re.search(r"SUGGESTIONS:\s*(\[.*?\])", full_text, re.DOTALL)
    if match:
        try:
            suggestions = json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
        full_text = full_text[: match.start()].strip()

    if not suggestions:
        suggestions = _CANNED_SUGGESTIONS

    return ChatResponse(reply=full_text, suggestions=suggestions)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def ai_chat(req: ChatRequest) -> ChatResponse:
    """Forward conversation to Gemini AI; fall back to canned response."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key:
        try:
            return await _gemini_chat(api_key, req)
        except Exception:
            return _canned_response(req)
    return _canned_response(req)
