import os

from databricks.sdk.service.sql import StatementParameterListItem, StatementState

from agent_server.databricks_clients import sp_workspace_client

WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
CATALOG = os.getenv("HOUSING_CATALOG", "housing")
SCHEMA = os.getenv("HOUSING_SCHEMA", "gold")


def execute_statement(statement: str, params: list[dict]) -> list[list]:
    """Run a parameterised SQL statement via Statement Execution API and return rows."""
    if not WAREHOUSE_ID:
        raise RuntimeError(
            "DATABRICKS_WAREHOUSE_ID is not set. "
            "Add it to .env — find it in Databricks UI → SQL Warehouses → Connection Details."
        )
    sdk_params = [
        StatementParameterListItem(name=p["name"], value=p["value"], type=p.get("type"))
        for p in params
    ]
    response = sp_workspace_client.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=statement,
        parameters=sdk_params,
        wait_timeout="30s",
    )
    if response.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(
            f"Statement execution failed: {response.status.state} — {response.status.error}"
        )
    return [list(row) for row in (response.result.data_array or [])]


def resolve_suburb_fuzzy(suburb_name: str, extra_cols: str = "") -> list[list]:
    """Resolve a colloquial suburb name to a DB row using exact-first, ILIKE fallback.

    Stats NZ SA2 names are granular (e.g. "Petone North", "Petone Central") while users
    pass colloquial names ("Petone"). This tries an exact match first; if none, falls back
    to ILIKE '%name%'. When multiple SA2s match the fuzzy pattern, the most populous one
    wins — that gives the best representative suburb for isochrone origins.

    Args:
        suburb_name: Colloquial suburb name from the LLM.
        extra_cols: Optional extra columns to SELECT (comma-prefixed string, e.g.
                    ", territorial_authority"). suburb_id and suburb_name are always returned.

    Returns:
        List with one row [suburb_id, suburb_name, ...extra_cols], or empty list if not found.
    """
    cols = f"suburb_id, suburb_name{extra_cols}"
    return execute_statement(
        f"""
        SELECT {cols}
        FROM {CATALOG}.{SCHEMA}.suburb
        WHERE suburb_name = :name
           OR suburb_name ILIKE :fuzzy
        ORDER BY
          CASE WHEN suburb_name = :name THEN 0 ELSE 1 END,
          population_2023 DESC NULLS LAST
        LIMIT 1
        """,
        [
            {"name": "name",  "value": suburb_name,        "type": "STRING"},
            {"name": "fuzzy", "value": f"%{suburb_name}%", "type": "STRING"},
        ],
    )
