"""State type for the product advisor LangGraph agent."""
from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class ProductAdvisorState(TypedDict):
    """
    Conversation state for the product advisor agent.

    messages:         LangGraph message list (HumanMessage, AIMessage, ToolMessage).
    product_context:  The scanned product data (from product_context.py).
    user_profile:     Optional dict with user's allergies, diet, conditions.
    session_id:       The testing portal session identifier.
    tools_called:     Names of tools called during this turn (for UI display).
    """
    messages: Annotated[list[BaseMessage], add_messages]
    product_context: dict[str, Any] | None
    user_profile: dict[str, Any] | None
    session_id: str
    tools_called: list[str]
