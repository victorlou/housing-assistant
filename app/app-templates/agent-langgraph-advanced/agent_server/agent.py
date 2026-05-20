import logging
import re
from datetime import datetime
from typing import Any, AsyncGenerator, Optional, Sequence, TypedDict

import mlflow
from databricks_langchain import ChatDatabricks
from fastapi import HTTPException
from langchain.agents import create_agent
from langchain_core.messages import AnyMessage
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langgraph.store.base import BaseStore
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
    to_chat_completions_input,
)
from typing_extensions import Annotated

from agent_server.prompts import SYSTEM_PROMPT
from agent_server.tools.compute_isochrone import compute_isochrone
from agent_server.tools.listing_urls import (
    build_barfoot_url,
    build_realestate_url,
    build_trademe_url,
)
from agent_server.tools.lookup_hazards import lookup_hazards
from agent_server.tools.score_affordability import score_affordability
from agent_server.utils import (
    _get_or_create_thread_id,
    init_mcp_client,
    process_agent_astream_events,
)
from agent_server.utils_memory import (
    get_lakebase_access_error_message,
    get_user_id,
    init_lakebase_config,
    lakebase_context,
    memory_tools,
)
from agent_server.databricks_clients import sp_workspace_client

logger = logging.getLogger(__name__)
mlflow.langchain.autolog()
logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)

LLM_ENDPOINT_NAME = "databricks-gpt-5-2"
LAKEBASE_CONFIG = init_lakebase_config()


@tool
def get_current_time() -> str:
    """Get the current date and time."""
    return datetime.now().isoformat()


@tool
def suggest_saved_search(
    suburb_name: str,
    median_rent_weekly: int,
    commute_minutes: int,
    commute_mode: str,
    hazard_risk: str,
    affordability_band: str,
) -> dict:
    """Frontend trigger: suggest saving a suburb recommendation to the user.
    Call once after recommending a specific suburb with concrete data (rent, commute,
    hazard, affordability band). Only call for data-backed recommendations — not for
    vague mentions or suburb lists. Do not call more than once per suburb per response."""
    return {"saved": True}


@tool
def generate_listing_links(
    suburbs: list[str],
    min_rent: int,
    max_rent: int,
    property_type: str = "house",
) -> dict:
    """Render listing link cards for NZ rental properties on the frontend.
    Call immediately when the user names a specific suburb AND states a budget AND uses
    rental/listing language ("find rentals", "show listings", "houses to rent", etc.).
    Also call after recommending suburbs when the user reacts positively.
    Do not narrate the URLs — the frontend renders the cards. One call covers all suburbs."""
    links = []
    for suburb in suburbs:
        links.append({
            "suburb": suburb,
            "realestate": build_realestate_url(suburb, min_rent, max_rent),
            "trademe": build_trademe_url(suburb, min_rent, max_rent),
            "barfoot": build_barfoot_url(suburb, min_rent, max_rent),
        })
    return {"listings": links, "render_widget": True}


@tool
def render_visualization(title: str, mermaid_code: str, description: str) -> dict:
    """Trigger a Mermaid diagram modal on the frontend. Call this after presenting
    multi-suburb comparisons, affordability decision trees, or hazard matrices to give
    users a visual summary. Validates the mermaid_code and returns an error with a
    fix hint if the syntax is structurally broken — fix and retry when that happens."""
    code = mermaid_code.strip()

    if not code.startswith("flowchart"):
        return {
            "status": "error",
            "error": "mermaid_code must start with 'flowchart TD' or 'flowchart LR'.",
            "hint": "Change the first line to 'flowchart TD' or 'flowchart LR' and call render_visualization again.",
        }

    lines = [ln.strip() for ln in code.splitlines() if ln.strip()]
    if len(lines) < 3:
        return {
            "status": "error",
            "error": "Diagram is too short — must have at least 2 nodes and 1 edge.",
            "hint": "Add more nodes/edges and call render_visualization again.",
        }

    for kw in ("classDef", "style ", "linkStyle", "subgraph", "click "):
        if kw in code:
            return {
                "status": "error",
                "error": f"'{kw.strip()}' is not allowed — use plain nodes and arrows only.",
                "hint": f"Remove all '{kw.strip()}' lines and call render_visualization again.",
            }

    if re.search(r"(?<!-)->(?!>)", code):
        return {
            "status": "error",
            "error": "Wrong arrow syntax: found '->' instead of '-->'.",
            "hint": "Replace every '->' with '-->' and call render_visualization again.",
        }

    return {"status": "rendered"}


class StatefulAgentState(TypedDict, total=False):
    messages: Annotated[Sequence[AnyMessage], add_messages]
    custom_inputs: dict[str, Any]
    custom_outputs: dict[str, Any]


async def init_agent(
    store: BaseStore,
    checkpointer: Optional[Any] = None,
):
    tools = [
        get_current_time,
        compute_isochrone,
        score_affordability,
        lookup_hazards,
        suggest_saved_search,
        render_visualization,
        generate_listing_links,
    ] + memory_tools()
    # To use MCP server tools instead, uncomment the below lines:
    mcp_client = init_mcp_client(sp_workspace_client)
    try:
        tools.extend(await mcp_client.get_tools())
    except Exception:
        logger.warning(
            "Failed to fetch MCP tools. Continuing without MCP tools.", exc_info=True
        )

    model = ChatDatabricks(endpoint=LLM_ENDPOINT_NAME)

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
        store=store,
        state_schema=StatefulAgentState,
    )


@invoke()
async def invoke_handler(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    outputs = [
        event.item
        async for event in stream_handler(request)
        if event.type == "response.output_item.done"
    ]

    custom_outputs: dict[str, Any] = {}
    if user_id := get_user_id(request):
        custom_outputs["user_id"] = user_id
    return ResponsesAgentResponse(output=outputs, custom_outputs=custom_outputs)


@stream()
async def stream_handler(
    request: ResponsesAgentRequest,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    thread_id = _get_or_create_thread_id(request)
    mlflow.update_current_trace(metadata={"mlflow.trace.session": thread_id})

    user_id = get_user_id(request)
    if not user_id:
        logger.warning("No user_id provided - memory features will not be available")

    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if user_id:
        config["configurable"]["user_id"] = user_id

    input_state: dict[str, Any] = {
        "messages": to_chat_completions_input([i.model_dump() for i in request.input]),
        "custom_inputs": dict(request.custom_inputs or {}),
    }

    try:
        async with lakebase_context(LAKEBASE_CONFIG) as (checkpointer, store):
            config["configurable"]["store"] = store

            agent = await init_agent(
                store=store, checkpointer=checkpointer
            )  # SP client used inside tools

            # process_agent_astream_events - works on agent.astream - which emits events and then our below function handles emission on their end
            async for event in process_agent_astream_events(
                agent.astream(input_state, config, stream_mode=["updates", "messages"])
            ):
                yield event
    except Exception as e:
        error_msg = str(e).lower()
        # Check for Lakebase access/connection errors
        if any(
            keyword in error_msg
            for keyword in ["lakebase", "pg_hba", "postgres", "database instance"]
        ):
            logger.error("Lakebase access error: %s", e)
            raise HTTPException(
                status_code=503,
                detail=get_lakebase_access_error_message(LAKEBASE_CONFIG.description),
            ) from e
        raise
