# Lakehouse Seed Data & SP Client Guide

How to write synthetic test data into the `workspace.test` Unity Catalog schema using the same service principal credentials the agent server already uses. This lets you develop and test agent tools against realistic NZ data without touching `housing.gold`.

---

## Two Databricks Clients — When to Use Each

The agent server uses two distinct clients sourced from the same credentials:

| Client | Import | Auth source | Use for |
|---|---|---|---|
| `WorkspaceClient` | `from databricks.sdk import WorkspaceClient` | `DATABRICKS_CONFIG_PROFILE` or env vars | REST APIs: Genie queries, statement execution (SQL reads), app management |
| `DatabricksSession` | `from databricks.connect import DatabricksSession` | `DATABRICKS_CONFIG_PROFILE` or env vars | Spark SQL: reading/writing Delta tables, ETL, seed scripts |

Both read from the same `~/.databrickscfg` profile set by `DATABRICKS_CONFIG_PROFILE` (or from `DATABRICKS_HOST` + `DATABRICKS_TOKEN` env vars).

### WorkspaceClient — already in agent_server

```python
# agent_server/agent.py:41
sp_workspace_client = WorkspaceClient()   # reads profile from env/config
```

Use this inside tool functions for lightweight SQL reads via the Statement Execution API:

```python
from databricks.sdk import WorkspaceClient

client = WorkspaceClient()
result = client.statement_execution.execute_statement(
    warehouse_id="your-warehouse-id",          # set DATABRICKS_WAREHOUSE_ID env var
    statement="SELECT * FROM housing.gold.rent__month__suburb WHERE suburb_name = :suburb",
    parameters=[{"name": "suburb", "value": "Onehunga", "type": "STRING"}],
    catalog="housing",
    schema="gold",
    wait_timeout="30s",
)
rows = [list(r) for r in result.result.data_array]
```

### DatabricksSession — for seed scripts and pipelines

```python
import os
from databricks.connect import DatabricksSession

spark = (
    DatabricksSession.builder
    .profile(os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT"))
    .serverless(True)          # or .clusterId("abc123") for an existing cluster
    .getOrCreate()
)

df = spark.createDataFrame(rows, schema=spark_schema)
df.write.format("delta").mode("overwrite").saveAsTable("workspace.test.suburb")
```

---

## Test Namespace: `workspace.test`

All seed data is written to `workspace.test.*` — the built-in `workspace` Unity Catalog, `test` schema. Column definitions mirror `housing.gold.*` exactly so tool code can switch between them with a single env var change.

### Why `workspace.test` and not `housing.test`?

- `housing` catalog requires explicit grants from the catalog owner; `workspace` catalog allows self-service schema creation for SP principals
- Keeps test data entirely separate from production data lineage
- Easier to wipe without risking Genie or dashboard dependencies

### Schema mirrors gold exactly

The seed script creates tables with the same column names and types as documented in [`lakehouse-gold-schema.md`](lakehouse-gold-schema.md). Tools switch between test and prod via `HOUSING_CATALOG` + `HOUSING_SCHEMA` env vars (see [agent-tool-extension-guide.md](agent-tool-extension-guide.md)).

---

## Running the Seed Script

**Script location:** `app/app-templates/agent-langgraph-advanced/scripts/generate_test_data.py`

### Prerequisites

1. `.env` in `agent-langgraph-advanced/` configured with working Databricks credentials
2. `databricks-connect` installed (`uv add databricks-connect` in the template virtualenv)
3. SP must have `CREATE SCHEMA` on `workspace` catalog **or** `workspace.test` must already exist
4. Compute available: serverless (easiest) or an existing cluster

### Dry-run first (no remote writes)

```bash
cd app/app-templates/agent-langgraph-advanced
uv run python scripts/generate_test_data.py
```

Prints the row counts for each table and exits — no Databricks connection made.

### Write with serverless compute (recommended)

```bash
uv run python scripts/generate_test_data.py --write --serverless
```

### Write with an existing cluster

```bash
uv run python scripts/generate_test_data.py --write --cluster-id <CLUSTER_ID>
```

### All flags

| Flag | Env var alternative | Purpose |
|---|---|---|
| `--write` | — | Required to actually write; omit for dry-run |
| `--serverless` | `DATABRICKS_SERVERLESS=true` | Use serverless Databricks Connect compute |
| `--cluster-id ID` | `DATABRICKS_CLUSTER_ID=ID` | Use a specific running cluster |
| `--profile NAME` | `DATABRICKS_CONFIG_PROFILE=NAME` | Databricks auth profile (default: `DEFAULT`) |
| `--reset` | — | Drop `workspace.test` before seeding (requires `--write`) |

The script is idempotent — `mode("overwrite")` means re-running replaces data cleanly.

### Expected output

```
[generate_test_data] DRY RUN — no data will be written.
[generate_test_data] Would write the following to workspace.test.*:

  workspace.test.suburb                            15 rows
  workspace.test.hazard                            45 rows
  workspace.test.isochrone                        225 rows
  workspace.test.rent__month__suburb            1,440 rows
  workspace.test.income__year__suburb              30 rows
  workspace.test.school                            15 rows

[generate_test_data] Re-run with --write to execute.
```

### Verify in Unity Catalog Explorer

After `--write`, open the Databricks UI → Catalog → `workspace` → `test` and check each table has rows.

---

## Permissions Needed for the SP

```sql
-- Run once as a workspace admin or catalog owner

-- Allow SP to create the test schema (workspace catalog is usually open to workspace users)
GRANT CREATE SCHEMA ON CATALOG workspace TO `sp-housing-app`;

-- Allow SP to read and write test tables
GRANT ALL PRIVILEGES ON SCHEMA workspace.test TO `sp-housing-app`;

-- Allow SP to read gold tables in production
GRANT SELECT ON SCHEMA housing.gold TO `sp-housing-app`;
```

> The SP gets no write permissions on `housing.gold` — read-only for production data.

---

## Resetting Test Data

```bash
# Drop and recreate from scratch
uv run python scripts/generate_test_data.py --write --serverless --reset
```

Or from the Databricks SQL console:

```sql
DROP SCHEMA IF EXISTS workspace.test CASCADE;
```

Then re-run the seed script.

---

**Author:** Naineel Soyantar | **Last Updated:** 2026-05-15
