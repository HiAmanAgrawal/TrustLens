"""
LangGraph StateGraph for the TrustLens conversational agent.

TOPOLOGY:
  [router] → conditional → [onboarding]              → END
                         → [existing_user_greeting]  → END

The compiled graph is a module-level singleton so it is built once at import
time and reused across requests.

DEPENDENCY INJECTION:
  Non-serialisable resources (AsyncSession) are passed via RunnableConfig:
    config = {"configurable": {"db_session": async_session}}
  This keeps the state TypedDict clean and serialisable.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from app.agents.nodes.greeting import existing_user_greeting_node
from app.agents.nodes.onboarding import onboarding_node
from app.agents.nodes.router import route_after_router, router_node
from app.agents.state import ConversationState

logger = logging.getLogger(__name__)


def _build_graph() -> object:
    builder: StateGraph = StateGraph(ConversationState)

    builder.add_node("router", router_node)
    builder.add_node("onboarding", onboarding_node)
    builder.add_node("existing_user_greeting", existing_user_greeting_node)

    builder.set_entry_point("router")
    builder.add_conditional_edges(
        "router",
        route_after_router,
        {
            "onboarding": "onboarding",
            "existing_user_greeting": "existing_user_greeting",
        },
    )
    builder.add_edge("onboarding", END)
    builder.add_edge("existing_user_greeting", END)

    compiled = builder.compile()
    logger.info("conversation_graph.compiled")
    return compiled


# Compiled graph singleton — import this everywhere you need to invoke the agent.
conversation_graph = _build_graph()
