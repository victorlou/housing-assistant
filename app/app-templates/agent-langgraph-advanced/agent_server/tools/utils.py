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
