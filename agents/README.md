# Agents

The AI agent that powers the consumer experience and any agentic capability used by the planner view.

Built with **LangGraph** (multi-step reasoning via StateGraph), **MLflow** (model logging & serving), and **Databricks** (data + compute).

## Quick Start

**New to the agent framework?** Start here:

1. **[docs/internal-workings/01-langgraph-agents-101.md](../docs/internal-workings/01-langgraph-agents-101.md)** — LangGraph fundamentals (20 min)
2. **[docs/internal-workings/02-agent-implementation-guide.md](../docs/internal-workings/02-agent-implementation-guide.md)** — Housing Assistant design (40 min)
3. **[docs/internal-workings/03-mlflow-evaluation-deployment.md](../docs/internal-workings/03-mlflow-evaluation-deployment.md)** — MLflow workflow (30 min)
4. **[docs/internal-workings/04-lakebase-auth-state.md](../docs/internal-workings/04-lakebase-auth-state.md)** — User state & access control (25 min)

Then follow the **Day 1-5 development roadmap** in guide 02.

## Layout

```
agents/
├── state.py                # AgentState definition
├── agent.py                # StateGraph + node definitions
├── tools/                  # One file per @tool function
│   ├── __init__.py
│   ├── query_genie.py      # Query Genie for housing data
│   ├── compute_isochrone.py
│   ├── score_affordability.py
│   ├── lookup_hazards.py
│   ├── save_user_profile.py
│   └── set_alert.py
├── prompts/
│   └── system.md           # System prompt (loaded at runtime)
├── deploy.py               # MLflow logging & serving endpoint
├── eval/
│   └── golden_dataset.jsonl # Test cases for evaluation
├── tests/                  # Unit tests (TODO)
├── requirements.txt
└── README.md               # You are here
```

## Tool Contracts

Every tool is a `@tool`-decorated function with:
- **Typed signature** — LLM can see argument types
- **Clear docstring** — LLM reads this to decide when to call
- **Return type** — Structured data (not strings)

Example:

```python
@tool
def compute_isochrone(origin_h3: str, mode: str, minutes: int) -> list[str]:
    """
    Return H3 cells reachable from origin_h3 in minutes or fewer.
    
    mode: "transit" | "drive" | "walk"
    minutes: Travel time limit (e.g., 30)
    """
    # Implementation
```

## The Six Tools

| Tool | Purpose |
|------|---------|
| **query_genie** | Q&A over housing data (rents, schools, income) |
| **compute_isochrone** | Suburbs reachable in N minutes by mode |
| **score_affordability** | Apply affordability rules; return 0.0-1.0 |
| **lookup_hazards** | Natural hazard risks (flood, coastal, liquefaction) |
| **save_user_profile** | Persist constraints to Lakebase |
| **set_alert** | Register saved search with alerts |

## Conventions

- **Tools are pure** — Read from lakehouse/Lakebase; no hidden state
- **Agent invokes Genie via tool** — Never direct HTTP calls
- **Prompts as files** — Load from `prompts/system.md` at runtime
- **User context via env vars** — `CURRENT_USER_ID`, `CURRENT_SESSION_ID`
- **All calls logged** — Conversation history in `housing.app.conversation_turns`

## Local Development

### Setup

```bash
cd agents
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Run the Agent

```python
from agent import agent_graph
from state import AgentState

# Invoke the agent
result = agent_graph.invoke({
    "messages": [{"role": "user", "content": "Find suburbs under $700/week"}],
    "user_id": "test-user",
    "session_id": "test-session",
})

print(result["messages"][-1].content)  # Agent's response
```

### Run Tests

```bash
pytest tests/
```

### Deploy to MLflow

```bash
# Log model to MLflow
python deploy.py dev

# Evaluate (if golden_dataset.jsonl exists)
python deploy.py staging
```

## System Prompt

Loaded from `prompts/system.md`. Defines:
- **Persona** — Warm, direct, honest
- **Task** — Help users find affordable suburbs
- **Tool use policy** — When/how to use each tool
- **Disambiguation rule** — Ask clarifying Q if ambiguous
- **Output format** — 3 ranked suburbs with explanations

See the file for full details and examples.

## StateGraph Structure

Three nodes:

1. **inject_context** — Sets env vars (user_id, session_id)
2. **agent** — LLM decides (answer, call tools, or clarify)
3. **tools** — ToolNode invokes tools and appends results

Flow: START → inject_context → agent → [tools → agent]* → END

See [docs/internal-workings/02-agent-implementation-guide.md](../docs/internal-workings/02-agent-implementation-guide.md) for the full graph diagram.

## Debugging

**Check agent traces:**
```sql
SELECT * FROM housing.app.conversation_turns
WHERE user_id = 'test-user'
ORDER BY created_at DESC
LIMIT 10;
```

**See tool calls:**
Print in the `inject_context` or `tools` node to debug state flow.

**MLflow experiments:**
```bash
cd agents
mlflow ui
# Open http://localhost:5000
```

## See Also

- [docs/architecture.md](../docs/architecture.md) — System design
- [docs/runbook.md](../docs/runbook.md) — Developer workflow
- [docs/internal-workings/](../docs/internal-workings/) — Deep dives
