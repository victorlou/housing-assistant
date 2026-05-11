"""Housing Assistant agent graph."""

import os
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from databricks_langchain import ChatDatabricks

from state import AgentState
from tools import (
    query_genie,
    compute_isochrone,
    score_affordability,
    lookup_hazards,
    save_user_profile,
    set_alert,
)


def inject_context(state: AgentState) -> AgentState:
    """
    Pre-agent setup node.

    Sets environment variables for CURRENT_USER_ID and CURRENT_SESSION_ID
    so tools can read them without threading through every function call.
    """
    if state.get("user_id"):
        os.environ["CURRENT_USER_ID"] = state["user_id"] or "unknown_user"
    if state.get("session_id"):
        os.environ["CURRENT_SESSION_ID"] = state["session_id"] or "unknown_session"

    # No change to state
    return state


def agent(state: AgentState) -> AgentState:
    """
    LLM decision node.

    The LLM reads the conversation history and decides:
    1. Answer directly (no tool calls)
    2. Call tools (query_genie, compute_isochrone, etc.)
    3. Ask a clarifying question
    """
    # Load system prompt from file
    with open("agents/prompts/system.md") as f:
        system_prompt = f.read()

    # Initialize LLM with tool binding
    llm = ChatDatabricks(model="databricks-claude-sonnet-4-5")

    # Bind all tools to LLM
    tools = [
        query_genie,
        compute_isochrone,
        score_affordability,
        lookup_hazards,
        save_user_profile,
        set_alert,
    ]
    llm_with_tools = llm.bind_tools(tools)

    # Get message history from state
    messages = state["messages"]

    # Invoke LLM with system prompt
    # TODO: Verify ChatDatabricks supports system_prompt parameter
    response = llm_with_tools.invoke(messages)

    # Return updated state with LLM response
    return {"messages": messages + [response]}


def should_continue(state: AgentState) -> Literal["tools", "end"]:
    """
    Routing function.

    If LLM called tools, route to tools node.
    Otherwise, end the conversation.
    """
    last_message = state["messages"][-1]

    # Check if LLM generated tool calls
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    else:
        return "end"


# Build the graph
def build_agent_graph():
    """Compile the StateGraph."""
    builder = StateGraph(AgentState)

    # Add nodes
    builder.add_node("inject_context", inject_context)
    builder.add_node("agent", agent)

    # Tool node (ToolNode handles invocation and result appending)
    tools = [
        query_genie,
        compute_isochrone,
        score_affordability,
        lookup_hazards,
        save_user_profile,
        set_alert,
    ]
    tool_node = ToolNode(tools)
    builder.add_node("tools", tool_node)

    # Add edges
    builder.add_edge("START", "inject_context")
    builder.add_edge("inject_context", "agent")

    # Conditional edge: if tools were called, go to tools node; else end
    builder.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END,
        },
    )

    # After tools are invoked, loop back to agent
    builder.add_edge("tools", "agent")

    # Compile and return
    return builder.compile()


# Instantiate the graph
agent_graph = build_agent_graph()
