"""Query Genie for housing data."""

from langchain_core.tools import tool
import os


@tool
def query_genie(question: str) -> list[dict]:
    """
    Ask a question about NZ housing data via Genie.

    Examples:
    - "suburbs with median rent under $700/week"
    - "schools in Auckland with decile >= 7"
    - "income deciles by territorial authority"

    Args:
        question: Natural language question about housing data

    Returns:
        List of dicts with query results from Genie
    """
    # TODO: Implement Genie API call
    # 1. Get Databricks WorkspaceClient
    # 2. Call client.genie.query(space_id="...", question=question)
    # 3. Poll until response.state == "COMPLETED"
    # 4. Parse response.result.value and return as list[dict]

    # Stub: Return empty list for now
    print(f"[STUB] query_genie: {question}")
    return []
