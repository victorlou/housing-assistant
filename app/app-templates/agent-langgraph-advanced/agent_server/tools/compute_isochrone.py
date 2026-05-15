import json
import logging
import os

from databricks.sdk.service.sql import StatementParameterListItem, StatementState
from langchain_core.tools import tool

from agent_server.databricks_clients import sp_workspace_client

logger = logging.getLogger(__name__)

WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
_CATALOG = os.getenv("HOUSING_CATALOG", "housing")
_SCHEMA = os.getenv("HOUSING_SCHEMA", "gold")


def _execute(statement: str, params: list[dict]) -> list[list]:
    """Run a SQL statement via Statement Execution API and return rows."""
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


@tool
def compute_isochrone(suburb_name: str, mode: str, minutes: int) -> dict:
    """
    Return suburbs reachable from a given suburb within a travel time limit.

    Use when the user asks about commute time, travel distance to work, or wants
    to know what areas are accessible within N minutes from a suburb.

    Args:
        suburb_name: Origin suburb name (e.g. "Onehunga", "Mt Albert")
        mode: Travel mode — "transit", "drive", or "walk"
        minutes: Maximum travel time in minutes (e.g. 30)

    Returns:
        Dict with:
          - origin: suburb name used as origin
          - mode: travel mode
          - minutes: time limit applied
          - reachable_suburbs: list of suburb names reachable within the time limit
          - reachable_cell_count: number of H3 cells reachable (proxy for area coverage)
    """
    # Step 1: resolve suburb name → h3_centroid
    centroid_rows = _execute(
        f"SELECT h3_centroid FROM {_CATALOG}.{_SCHEMA}.suburb WHERE suburb_name = :suburb LIMIT 1",
        [{"name": "suburb", "value": suburb_name, "type": "STRING"}],
    )
    if not centroid_rows or not centroid_rows[0][0]:
        return {
            "origin": suburb_name,
            "mode": mode,
            "minutes": minutes,
            "reachable_suburbs": [],
            "reachable_cell_count": 0,
            "error": f"Suburb '{suburb_name}' not found in housing data.",
        }
    h3_origin = centroid_rows[0][0]

    # Step 2: fetch h3_destinations for the closest minutes_bucket >= requested minutes
    iso_rows = _execute(
        f"""
        SELECT h3_destinations
        FROM {_CATALOG}.{_SCHEMA}.isochrone
        WHERE h3_origin = :h3_origin
          AND mode = :mode
          AND minutes_bucket = (
            SELECT MIN(minutes_bucket)
            FROM {_CATALOG}.{_SCHEMA}.isochrone
            WHERE h3_origin = :h3_origin
              AND mode = :mode
              AND minutes_bucket >= :minutes
          )
        LIMIT 1
        """,
        [
            {"name": "h3_origin", "value": h3_origin, "type": "STRING"},
            {"name": "mode", "value": mode, "type": "STRING"},
            {"name": "minutes", "value": str(minutes), "type": "INT"},
        ],
    )
    if not iso_rows or not iso_rows[0][0]:
        return {
            "origin": suburb_name,
            "mode": mode,
            "minutes": minutes,
            "reachable_suburbs": [],
            "reachable_cell_count": 0,
        }

    # h3_destinations is returned as a JSON array string by the Statement Execution API
    raw = iso_rows[0][0]
    h3_destinations: list[str] = json.loads(raw) if isinstance(raw, str) else list(raw)

    # Step 3: resolve destination cells → suburb names
    reachable_suburbs: list[str] = []
    if h3_destinations:
        placeholders = ", ".join(f"'{c}'" for c in h3_destinations)
        suburb_rows = _execute(
            f"""
            SELECT DISTINCT suburb_name
            FROM {_CATALOG}.{_SCHEMA}.suburb
            WHERE h3_centroid IN ({placeholders})
              AND suburb_name != :origin
            ORDER BY suburb_name
            """,
            [{"name": "origin", "value": suburb_name, "type": "STRING"}],
        )
        reachable_suburbs = [row[0] for row in suburb_rows if row[0]]

    return {
        "origin": suburb_name,
        "mode": mode,
        "minutes": minutes,
        "reachable_suburbs": reachable_suburbs,
        "reachable_cell_count": len(h3_destinations),
    }
