# Agent Backend Architecture

> How the `agent-langgraph-advanced` template works end-to-end — endpoints, request/response types, LangGraph execution, and the streaming translation layer.

**Template path:** `app/app-templates/agent-langgraph-advanced/`
Advanced LangGraph template with short-term memory (checkpointer), long-term memory (store), and background task support.

---

## Entry Point: `agent_server/start_server.py`

- Loads `.env` before anything else (auth config must be set before agent imports)
- Instantiates `AgentServer(LongRunningAgentServer)` — a Databricks AI Bridge class that creates a FastAPI app and registers HTTP routes automatically
- `import agent_server.agent` (line 21) is the trigger: importing the module executes `@invoke()` and `@stream()` decorators, registering the handlers with the server's internal registry
- The FastAPI `app` object is exposed at module level for multi-worker support: `app = agent_server.app`

**Routes registered (automatically by LongRunningAgentServer):**
- `POST /responses` (alias: `POST /invocations`) — main chat endpoint
- `GET  /responses/{id}` — background task polling/streaming resume

---

## How `@invoke` and `@stream` Work

Both live in `agent_server/agent.py`. They don't define separate routes — they register **handlers** against the single `POST /responses` endpoint. The server dispatches based on the `stream` field in the request body:

| Request has | Handler called | Response |
|---|---|---|
| `stream: false` (default) | `invoke_handler` (`@invoke`) | Full JSON after agent finishes |
| `stream: true` | `stream_handler` (`@stream`) | SSE stream of events |
| `background: true` | either, but returns `id` immediately | Client polls `GET /responses/{id}` |

---

## `ResponsesAgentRequest` — The Input Type

Defined by MLflow (`mlflow.types.responses`). The server deserializes the HTTP POST body into this Pydantic model before calling your handler.

```
ResponsesAgentRequest
  .input          → list of OpenAI-style messages: [{role, content}]
  .stream         → bool: SSE or JSON?
  .background     → bool: async execution?
  .custom_inputs  → dict: anything non-standard (thread_id, user_id go here)
  .context        → ChatContext with .conversation_id (fallback for thread_id)
```

**How `stream_handler` uses it (`agent.py:99`):**
1. `_get_or_create_thread_id(request)` — checks `custom_inputs["thread_id"]`, then `context.conversation_id`, then generates a UUID7
2. `get_user_id(request)` — reads `custom_inputs["user_id"]`
3. `to_chat_completions_input([i.model_dump() for i in request.input])` — converts OpenAI message list → LangChain `HumanMessage`/`AIMessage` objects

---

## Where the Agent Is Actually Called

`agent.py:118-129` inside `stream_handler`:

```python
async with lakebase_context(LAKEBASE_CONFIG) as (checkpointer, store):
    agent = await init_agent(store=store, checkpointer=checkpointer)
    async for event in process_agent_astream_events(
        agent.astream(input_state, config, stream_mode=["updates", "messages"])
    ):
        yield event
```

- `lakebase_context` — opens a Postgres connection to Lakebase, returns `checkpointer` (short-term memory) and `store` (long-term memory)
- `init_agent()` — builds the LangGraph ReAct agent: `ChatDatabricks` model + tools + memory wired in
- `agent.astream(...)` — **the actual agent loop**. LangGraph runs: LLM inference → tool selection → tool execution → loop back to LLM
- `stream_mode=["updates", "messages"]` — emits two event types:
  - `"messages"` → raw token chunks as they stream from the LLM
  - `"updates"` → completed node outputs (finalized tool calls, tool results, final messages)

---

## `process_agent_astream_events` — The Translation Layer

**File:** `agent_server/utils.py:84`

LangGraph speaks its own event format. The frontend expects OpenAI Responses API SSE format. This function translates in real-time.

**LangGraph emits tuples:**
```
("messages", [AIMessageChunk(content="Hello", tool_call_chunks=[...])])
("updates",  {"agent": {"messages": [AIMessage(...), ToolMessage(...)]}, ...})
```

**Translation table:**

| LangGraph event | Scenario | → ResponsesAgentStreamEvent type |
|---|---|---|
| `messages` + `AIMessageChunk` text | Token streaming | `response.output_text.delta` |
| `messages` + `AIMessageChunk` tool chunks | Tool call building | `response.function_call_arguments.delta` |
| `updates` + `AIMessage` with `tool_calls` | Tool call finalized | `response.output_item.done` (function_call) |
| `updates` + `ToolMessage` | Tool result returned | `response.output_item.done` (function_call_output) |
| `updates` + `AIMessage` with `content` | Final text response | `response.output_item.done` (message) |

**State machine inside the function:**
- `in_turn` / `_start_turn()` / `_end_turn()` — tracks whether the agent is mid-response, to know when to emit `response.created` and `response.completed` bookend events
- `active_tool_calls: dict[int, dict]` — accumulates streaming tool call chunks by index before finalizing
- `active_text_item_id` — tracks the current streaming text item so delta events share the same `item_id`

**ID handling:** Streaming responses use a fake placeholder ID (`resp_placeholder_xxx`) because the real `response_id` is only known by `LongRunningAgentServer`. `AgentServer.transform_stream_event()` calls `replace_fake_id()` to swap it in.

---

## `ResponsesAgentResponse` — The Non-Streaming Return

When `stream: false`, `invoke_handler` runs `stream_handler` internally and collects only `response.output_item.done` events:

```python
outputs = [event.item async for event in stream_handler(request)
           if event.type == "response.output_item.done"]
return ResponsesAgentResponse(output=outputs, custom_outputs=custom_outputs)
```

```
ResponsesAgentResponse
  .output          → list of completed output items (messages, tool calls, tool outputs)
  .custom_outputs  → dict: carries thread_id / user_id back to client for session reuse
```

---

## Memory System

| Type | Class | ID field | Scope |
|---|---|---|---|
| Short-term | `AsyncCheckpointSaver` (Lakebase) | `thread_id` | Within a conversation session |
| Long-term | `AsyncDatabricksStore` (Lakebase) | `user_id` | Across all sessions for a user |

Both IDs come from `custom_inputs` in the request. The client must send the same `thread_id` on every turn to maintain conversation continuity.

---

## Complete Data Flow

```
Frontend POST /responses
  { input: [{role:"user", content:"..."}], stream:true,
    custom_inputs: {thread_id:"abc", user_id:"email@zuru.com"} }
        │
        ▼
LongRunningAgentServer → deserializes → ResponsesAgentRequest
        │ (stream:true)
        ▼
stream_handler(request)               [agent.py:98]
  ├── extract thread_id, user_id
  ├── build LangGraph config with checkpointer + store
  ├── init_agent() → LangGraph ReAct agent
  └── agent.astream(messages, config)   ← AGENT LOOP
            │
            ▼
     process_agent_astream_events()     [utils.py:84]
       ├── "messages" events → token deltas → response.output_text.delta
       ├── "updates" tool calls → response.output_item.done (function_call)
       └── "updates" tool results → response.output_item.done (function_call_output)
        │
        ▼
SSE stream to frontend:
  response.created → response.output_text.delta (×N) → response.output_item.done → response.completed → [DONE]
```

---

## Key Files

| File | Purpose |
|---|---|
| `agent_server/start_server.py` | Server entry point, `AgentServer`, lifespan (Lakebase setup) |
| `agent_server/agent.py` | `@invoke` + `@stream` handlers, `init_agent()`, LangGraph wiring |
| `agent_server/utils.py` | `process_agent_astream_events()`, thread_id extraction, MCP client init |
| `agent_server/utils_memory.py` | Long-term memory tools, Lakebase config + context manager |
| `agent_server/prompts.py` | System prompt |
| `databricks.yml` | Bundle config, resource permissions for tools |

---

## Frontend Integration Notes

When calling from the housing assistant chat UI:

- Pass `thread_id` per chat session (generate once on session start, reuse every turn)
- Pass `user_id` as the logged-in user's identifier (e.g. email)
- Use `stream: true` for chat UX — users see tokens appear as the agent responds
- For long-running housing searches, consider `background: true` + polling `GET /responses/{id}`
- Read `custom_outputs.thread_id` from the first response and store it if you let the server generate it
