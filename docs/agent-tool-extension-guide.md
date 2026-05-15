# Agent Tool Extension Guide

How to add a new tool to the Housing Assistant agent, implement an existing stub, and wire everything into the LangGraph agent server. The agent's LLM decides which tool to call based on the tool's docstring — you write the data logic; the agent handles routing.

---

## Architecture Overview

```
User message
     │
     ▼
LangGraph ReAct loop  (agent_server/agent.py)
     │
     ├─ LLM reads tool docstrings → decides which tool(s) to call
     │
     └─ tool function executes → result returned to LLM → LLM formulates answer
```

**Your job as a tool author:**
- Write a Python function with a clear docstring (the LLM reads this to decide when to call it)
- Query the right Unity Catalog table or Lakebase table
- Return a clean, readable string or dict (the LLM reads the result)

You never write routing logic. The LLM handles that.

---

## Tool Structure

Every tool is a Python function decorated with `@tool` from `langchain_core.tools`:

```python
from langchain_core.tools import tool

@tool
def score_affordability(suburb: str, household_income: int) -> float:
    """
    Score suburb affordability (0.0 = unaffordable, 1.0 = very affordable).

    Logic: rent ≤ 30% of weekly income = 1.0; score decreases linearly beyond that.

    Args:
        suburb: Suburb name (e.g. "Onehunga")
        household_income: Annual household income in NZD

    Returns:
        Affordability score between 0.0 and 1.0
    """
    # ... implementation
```

The **docstring is critical** — it's what the LLM reads to know:
- When to call this tool (Examples section helps)
- What arguments to pass
- What the return value means

---

## How Tools Get the WorkspaceClient

All tools use the **service principal** `WorkspaceClient` — initialized once at module level in `agent_server/agent.py` as `sp_workspace_client`. Tools import it from there via a shared singleton module.

**`agent_server/databricks_clients.py`** (create this file once):
```python
from databricks.sdk import WorkspaceClient
sp_workspace_client = WorkspaceClient()   # reads DATABRICKS_CONFIG_PROFILE / env vars
```

Then `agent_server/agent.py` and all tool files import from the same place — one initialization, no duplication:
```python
from agent_server.databricks_clients import sp_workspace_client
```

## Querying Unity Catalog from a Tool

### Statement Execution API (standard pattern for tools)

Fast, no Spark cluster overhead. Uses the SQL warehouse set in `DATABRICKS_WAREHOUSE_ID`.

```python
import os
from agent_server.databricks_clients import sp_workspace_client

WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
UC_CATALOG = os.getenv("HOUSING_CATALOG", "housing")    # "workspace" for dev
UC_SCHEMA = os.getenv("HOUSING_SCHEMA", "gold")         # "test" for dev

def _execute(sql: str, params: list[dict] | None = None) -> list[list]:
    result = sp_workspace_client.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=sql,
        parameters=params or [],
        catalog=UC_CATALOG,
        schema=UC_SCHEMA,
        wait_timeout="30s",
    )
    return [list(r) for r in (result.result.data_array or [])]
```

### DatabricksSession (for bulk reads / DataFrame operations)

Use only if you need DataFrame-level operations (large aggregations, multi-table joins). `databricks-connect` is already in `requirements.txt`.

```python
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.getOrCreate()
df = spark.table(f"{UC_CATALOG}.{UC_SCHEMA}.rent__month__suburb").filter(...)
```

---

## Environment Variables for Schema Targeting

Add these to `agent-langgraph-advanced/.env` to switch between test and prod data:

```bash
# Production (default)
HOUSING_CATALOG=housing
HOUSING_SCHEMA=gold

# Development — switch both to hit workspace.test.* seeded by generate_test_data.py
# HOUSING_CATALOG=workspace
# HOUSING_SCHEMA=test

DATABRICKS_WAREHOUSE_ID=abc123def456   # find in Databricks UI → SQL Warehouses
```

The same tool code hits `workspace.test.*` locally and `housing.gold.*` in production with no code changes — just env var swap.

---

## Implementing a Tool

Write new tools directly in `agent_server/` — the `agents/` directory at the project root is no longer used. Recommended locations:

- One-off tool: define the `@tool` function directly at the top of `agent_server/agent.py`
- Larger tool (needs helpers, its own imports): create `agent_server/tools/<name>.py` and import from there

### Example: implementing `compute_isochrone`

`agent_server/tools/compute_isochrone.py`:

```python
import os
from langchain_core.tools import tool
from agent_server.databricks_clients import sp_workspace_client

WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
CATALOG = os.getenv("HOUSING_CATALOG", "housing")    # "workspace" for dev
SCHEMA = os.getenv("HOUSING_SCHEMA", "gold")         # "test" for dev

@tool
def compute_isochrone(origin_h3: str, mode: str, minutes: int) -> list[str]:
    """
    Return H3 cells reachable from origin_h3 within the given travel time.

    Use when the user asks about commute distance, travel time to work,
    or what's accessible within N minutes.

    Args:
        origin_h3: H3 res-8 cell ID for the origin (e.g. "8928308291bfffff")
        mode: Travel mode — "transit", "drive", or "walk"
        minutes: Maximum travel time in minutes

    Returns:
        List of reachable H3 cell IDs
    """
    sql = f"""
        SELECT h3_destinations
        FROM {CATALOG}.{SCHEMA}.isochrone
        WHERE h3_origin = :h3_origin
          AND mode = :mode
          AND minutes_bucket = (
            SELECT MIN(minutes_bucket)
            FROM {CATALOG}.{SCHEMA}.isochrone
            WHERE h3_origin = :h3_origin
              AND mode = :mode
              AND minutes_bucket >= :minutes
          )
        LIMIT 1
    """
    rows = _execute(sql, [
        {"name": "h3_origin", "value": origin_h3, "type": "STRING"},
        {"name": "mode", "value": mode, "type": "STRING"},
        {"name": "minutes", "value": str(minutes), "type": "INT"},
    ])
    if not rows:
        return []
    return rows[0][0] or []   # h3_destinations is ARRAY<STRING>


def _execute(sql: str, params: list[dict]) -> list[list]:
    result = sp_workspace_client.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=sql,
        parameters=params,
        wait_timeout="30s",
    )
    return [list(r) for r in (result.result.data_array or [])]
```

---

## Wiring a Tool into the Agent

### Step 1 — Write the tool function

Create `agent_server/tools/<name>.py` (or add the function directly in `agent_server/agent.py` for small tools).

### Step 2 — Import in `agent_server/agent.py`

```python
# agent_server/agent.py — add import at the top
from agent_server.tools.compute_isochrone import compute_isochrone
from agent_server.tools.score_affordability import score_affordability
from agent_server.tools.lookup_hazards import lookup_hazards
```

### Step 3 — Add to the tools list

At `agent_server/agent.py:64`, extend the tools list:

```python
async def init_agent(store, workspace_client=None, checkpointer=None):
    tools = [
        get_current_time,
        compute_isochrone,        # ← add here
        score_affordability,      # ← add here
        lookup_hazards,           # ← add here
    ] + memory_tools()
```

### Step 4 — Confirm the system prompt covers the tool

`agent_server/prompts.py` already lists all six tools with descriptions. If you add a new tool, add a bullet in the `## Your tools` section:

```python
SYSTEM_PROMPT = """...
### Data and analysis tools
- **your_new_tool(arg1, arg2)** — Short description of when the agent should call this.
...
"""
```

### Step 5 — Test locally

```bash
uv run start-app   # starts the FastAPI server on localhost:8000

# In another terminal:
curl -s -X POST http://localhost:8000/responses \
  -H "Content-Type: application/json" \
  -d '{
    "input": [{"role": "user", "content": "What is the flood risk in Onehunga?"}],
    "stream": false,
    "custom_inputs": {"user_id": "test@example.com", "thread_id": "test-123"}
  }' | jq '.output[].content'
```

Check that the agent calls `lookup_hazards` and returns a result from the seeded test data.

---

## Adding a Brand-New Tool

Example: a tool that geocodes a suburb name to H3.

1. Create `agent_server/tools/suburb_to_h3.py` with `@tool def suburb_to_h3(suburb_name: str) -> str | None`
2. Query `{CATALOG}.{SCHEMA}.suburb` for `h3_centroid` where `suburb_name = :suburb` (reads from `workspace.test` during dev, `housing.gold` in prod)
3. Wire it in (Steps 2–4 above)
4. Update the system prompt so the LLM knows when to call it
5. Add an example in the docstring (e.g. "Use this before calling compute_isochrone when the user gives a suburb name instead of an H3 cell")

No routing code needed — the LLM reads the docstring and decides.

---

## Table Name Quick Reference

| Prod table (`housing.gold.*`) | Test table (`workspace.test.*`) | Old stub name (wrong — ignore) |
|---|---|---|
| `housing.gold.suburb` | `workspace.test.suburb` | `dim_suburb` |
| `housing.gold.hazard` | `workspace.test.hazard` | `dim_hazard` |
| `housing.gold.isochrone` | `workspace.test.isochrone` | `fact_isochrone` |
| `housing.gold.rent__month__suburb` | `workspace.test.rent__month__suburb` | `fact_rent_by_suburb_month` |
| `housing.gold.income__year__suburb` | `workspace.test.income__year__suburb` | — |
| `housing.gold.school` | `workspace.test.school` | — |

Full column definitions: [`lakehouse-gold-schema.md`](lakehouse-gold-schema.md)

---

## Testing Against Synthetic Data

Before running against real `housing.gold.*`:

1. Set `HOUSING_CATALOG=workspace` and `HOUSING_SCHEMA=test` in `agent-langgraph-advanced/.env`
2. Seed the test tables: `uv run python scripts/generate_test_data.py --write --serverless`
3. Start the agent: `uv run start-app`
4. Test with a suburb from the seed data (e.g. "Onehunga", "Mt Albert", "Sandringham")

For production deployment, revert to `HOUSING_CATALOG=housing` and `HOUSING_SCHEMA=gold`.

---

**Author:** Naineel Soyantar | **Last Updated:** 2026-05-15
