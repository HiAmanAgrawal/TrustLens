"""
Product Advisor LangGraph agent.

TOPOLOGY (ReAct loop):
  [inject_context] → [llm_with_tools] ─── tool needed? ──→ [tool_executor] ─┐
                             ↑                                                │
                             └────────────────────────────────────────────────┘
                             └── no more tools → END

AGENT ROLE:
  A nutrition and health advisor (not a doctor). Answers follow-up questions
  about scanned products using the structured product context as grounded truth.
  Calls tools for web searches, DB lookups, suitability checks, and scoring.

LLM BACKBONE SELECTION (in priority order):
  1. Claude (langchain-anthropic) — if ANTHROPIC_API_KEY is set
  2. Google Gemini (langchain-google-genai) — if GOOGLE_API_KEY is set
  3. OpenAI / LM Studio (langchain-openai) — if OPENAI_API_KEY is set

WHY use create_react_agent from langgraph_prebuilt:
  It handles the tool-call loop, message accumulation, and interrupt-on-finish
  logic without boilerplate. We only need to supply the LLM + tools + system prompt.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

_BASE_SYSTEM = """\
You are TrustLens Product Advisor — a nutrition and food safety assistant.

Your job is to help users understand their scanned grocery or medicine products
by answering follow-up questions grounded in the product data below.

RULES:
1. Answer ONLY based on the product context + tool results. Do not hallucinate.
2. Be specific: quote actual numbers (e.g. "15g sugar per 100g") not vague claims.
3. For health questions, use the assess_suitability tool first.
4. For unknown details, use search_web with a targeted query.
5. NEVER make medical diagnoses. Always add the disclaimer for health questions:
   "⚕️ This is informational only. Consult a doctor or dietitian for medical advice."
6. For trust/quality questions, use calculate_trust_score.
7. Keep answers concise — 3-6 sentences unless the user asks for detail.
8. If the product context is missing, say so clearly and offer to help with a new scan.
"""


def _build_system_prompt(product_context: dict | None, user_profile: dict | None) -> str:
    """Inject current product context and user profile into the system prompt."""
    parts = [_BASE_SYSTEM]

    if product_context:
        # Format as readable JSON for the LLM
        parts.append("\n---\n📦 SCANNED PRODUCT CONTEXT:\n")
        # Only include non-null fields to keep the prompt lean
        compact = {k: v for k, v in product_context.items() if v not in (None, [], {})}
        parts.append(json.dumps(compact, indent=2, default=str)[:4000])
    else:
        parts.append("\n---\n⚠️ No product has been scanned yet in this session.")

    if user_profile:
        parts.append("\n---\n👤 USER PROFILE:\n")
        parts.append(json.dumps(user_profile, indent=2, default=str)[:1000])

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def _build_llm() -> Any:
    """
    Return a LangChain chat model with tool-calling support.

    Priority order:
      1. Anthropic Claude (claude-sonnet-4-6)  — best tool-calling accuracy
      2. Google Gemini (gemini-2.0-flash)       — fast, free tier available
      3. LM Studio (Qwen3 chat model)           — local, private, no API cost
      4. OpenAI cloud (gpt-4o-mini)             — reliable fallback

    LM Studio is probed with a quick sync GET before being selected so the
    server startup error surfaces immediately instead of at first tool call.
    """
    from app.core.config import get_settings
    s = get_settings()

    # ── 1. Anthropic Claude ──────────────────────────────────────────────────
    if s.anthropic_api_key:
        logger.info("product_advisor.llm | provider=anthropic model=claude-sonnet-4-6")
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            api_key=s.anthropic_api_key,
            model="claude-sonnet-4-6",
            max_tokens=1024,
            temperature=0.3,
        )

    # ── 2. Google Gemini ─────────────────────────────────────────────────────
    if s.google_api_key:
        logger.info("product_advisor.llm | provider=gemini model=gemini-2.0-flash")
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                google_api_key=s.google_api_key,
                model="gemini-2.0-flash",
                temperature=0.3,
                max_output_tokens=1024,
            )
        except ImportError:
            logger.warning("product_advisor.llm | langchain-google-genai not installed, skipping")

    # ── 3. LM Studio (Qwen3 or any local chat model) ────────────────────────
    if _lm_studio_chat_available(s.lm_studio_base_url, s.lm_studio_health_timeout_s):
        logger.info(
            "product_advisor.llm | provider=lm_studio model=%s @ %s",
            s.lm_studio_chat_model, s.lm_studio_base_url,
        )
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            api_key=s.lm_studio_api_key,
            base_url=s.lm_studio_base_url,
            model=s.lm_studio_chat_model,
            temperature=0.3,
            max_tokens=1024,
        )

    # ── 4. OpenAI cloud ──────────────────────────────────────────────────────
    if s.openai_api_key and "localhost" not in s.openai_base_url:
        logger.info(
            "product_advisor.llm | provider=openai model=gpt-4o-mini @ %s", s.openai_base_url,
        )
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            api_key=s.openai_api_key,
            base_url=s.openai_base_url,
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=1024,
        )

    raise RuntimeError(
        "No LLM provider available for product advisor. "
        "Set one of: ANTHROPIC_API_KEY, GOOGLE_API_KEY, or start LM Studio "
        "(LM_STUDIO_BASE_URL defaults to http://localhost:1234/v1)."
    )


def _lm_studio_chat_available(base_url: str, timeout: float) -> bool:
    """
    Synchronous health check for LM Studio before selecting it as provider.

    Uses requests (sync) because _build_llm() is called at import time outside
    an async context. A 2-second timeout means failing fast when LM Studio is
    not running, without blocking the startup meaningfully.
    """
    try:
        import urllib.request
        req = urllib.request.Request(f"{base_url}/models", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            alive = resp.status < 500
            logger.debug(
                "product_advisor._lm_studio_health | url=%s status=%d alive=%s",
                base_url, resp.status, alive,
            )
            return alive
    except Exception as exc:
        logger.debug("product_advisor._lm_studio_health | unreachable: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def _build_graph():
    """Build and compile the product advisor ReAct graph."""
    from langgraph.prebuilt import create_react_agent
    from app.agents.product_advisor.tools import ALL_TOOLS

    try:
        llm = _build_llm()
    except RuntimeError as exc:
        logger.error("product_advisor | cannot build graph: %s", exc)
        raise

    graph = create_react_agent(llm, tools=ALL_TOOLS)
    logger.info("product_advisor.graph.compiled | tools=%s", [t.name for t in ALL_TOOLS])
    return graph


# Lazy singleton — built on first use so import doesn't fail at startup
# if no API key is configured yet.
_graph_instance = None
_build_error: str | None = None


def _get_graph():
    global _graph_instance, _build_error
    if _graph_instance is not None:
        return _graph_instance
    if _build_error is not None:
        raise RuntimeError(_build_error)
    try:
        _graph_instance = _build_graph()
        return _graph_instance
    except Exception as exc:
        _build_error = str(exc)
        raise


# ---------------------------------------------------------------------------
# Public invoke function
# ---------------------------------------------------------------------------

async def run_product_advisor(
    question: str,
    *,
    product_context: dict | None = None,
    user_profile: dict | None = None,
    session_id: str = "default",
) -> dict[str, Any]:
    """
    Run the product advisor agent for a single user question.

    Returns a dict with:
      answer:       The agent's final text response.
      tools_called: List of tool names called during this turn.
      error:        Error message string if the agent failed.
    """
    logger.info(
        "product_advisor.run | session=%r q=%r context_present=%s",
        session_id, question[:80], bool(product_context),
    )

    try:
        graph = _get_graph()
    except RuntimeError as exc:
        logger.error("product_advisor.run | graph unavailable: %s", exc)
        return {
            "answer": (
                "⚠️ Product advisor is not configured. "
                "Set ANTHROPIC_API_KEY, GOOGLE_API_KEY, or OPENAI_API_KEY to enable it."
            ),
            "tools_called": [],
            "error": str(exc),
        }

    system_prompt = _build_system_prompt(product_context, user_profile)
    tools_called: list[str] = []

    from langchain_core.messages import HumanMessage, SystemMessage

    try:
        result = await graph.ainvoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=question),
                ]
            },
            config={"recursion_limit": 10},
        )

        # Collect tool names from the message history
        for msg in result.get("messages", []):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "?")
                    tools_called.append(name)
                    logger.info("product_advisor.tool_called | %s", name)

        # Final answer is the last AIMessage
        final_msg = result["messages"][-1]
        answer = final_msg.content if hasattr(final_msg, "content") else str(final_msg)

        logger.info(
            "product_advisor.done | session=%r tools=%s answer_len=%d",
            session_id, tools_called, len(answer),
        )
        return {"answer": answer, "tools_called": tools_called, "error": None}

    except Exception as exc:
        logger.exception("product_advisor.run | error session=%r", session_id)
        return {
            "answer": f"⚠️ Agent error: {exc}",
            "tools_called": tools_called,
            "error": str(exc),
        }


# Module-level alias used by the testing portal
product_advisor_graph = _get_graph
