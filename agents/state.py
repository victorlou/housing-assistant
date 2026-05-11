"""Agent state definition."""

from langgraph.graph import MessagesState
from typing import Optional


class AgentState(MessagesState):
    """
    Housing Assistant agent state.

    Carries conversation history (via MessagesState) plus project-specific fields.
    """

    # Injected by app (read-only for agent)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    results: Optional[dict] = None # Store results from tools or other sources, to be used in the conversation.
