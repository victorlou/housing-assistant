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
    """Resolve a colloquial suburb name to one or more DB rows using exact-first, ILIKE fallback.

    Stats NZ SA2 names are granular (e.g. "Petone North", "Petone Central") while users
    pass colloquial names ("Petone"). This tries an exact match first; if it finds one,
    returns only that row. If not, falls back to ILIKE '%name%' and returns ALL matching
    SA2s (up to 10), ordered by population descending — callers should aggregate across
    all returned rows rather than using only the first.

    Args:
        suburb_name: Colloquial suburb name from the LLM.
        extra_cols: Optional extra columns to SELECT (comma-prefixed string, e.g.
                    ", territorial_authority"). suburb_id and suburb_name are always returned.

    Returns:
        List of rows [suburb_id, suburb_name, ...extra_cols]. Returns all SA2s that match
        the fuzzy pattern (exact match short-circuits to 1 row; fuzzy can return many).
        Empty list if nothing found.
    """
    cols = f"suburb_id, suburb_name{extra_cols}"
    return execute_statement(
        f"""
        WITH exact AS (
          SELECT {cols}
          FROM {CATALOG}.{SCHEMA}.suburb
          WHERE suburb_name = :name
        ),
        fuzzy AS (
          SELECT {cols}
          FROM {CATALOG}.{SCHEMA}.suburb
          WHERE suburb_name ILIKE :fuzzy
            AND (SELECT COUNT(*) FROM exact) = 0
          ORDER BY population_2023 DESC NULLS LAST
          LIMIT 10
        )
        SELECT * FROM exact
        UNION ALL
        SELECT * FROM fuzzy
        """,
        [
            {"name": "name", "value": suburb_name, "type": "STRING"},
            {"name": "fuzzy", "value": f"%{suburb_name}%", "type": "STRING"},
        ],
    )


def build_in_params(ids: list[str], prefix: str = "id") -> tuple[str, list[dict]]:
    """Build a named-parameter IN clause for the Statement Execution API.

    Args:
        ids: List of string values to match against.
        prefix: Param name prefix (e.g. "oid" → :oid0, :oid1, ...).

    Returns:
        (placeholders, params) where placeholders is ":oid0, :oid1, ..." and
        params is the list of dicts to pass to execute_statement.
    """
    placeholders = ", ".join(f":{prefix}{i}" for i in range(len(ids)))
    params = [
        {"name": f"{prefix}{i}", "value": v, "type": "STRING"}
        for i, v in enumerate(ids)
    ]
    return placeholders, params
