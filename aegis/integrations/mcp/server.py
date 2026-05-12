"""Aegis MCP server — exposes Aegis DQ tools via the Model Context Protocol."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ...audit.trajectory import export_sharegpt, list_run_ids
from ...memory.store import DB_PATH

mcp_server = FastMCP("aegis-dq", instructions=(
    "Aegis DQ — agentic data quality framework. "
    "Use these tools to run validations, inspect audit trails, and analyze failures."
))


@mcp_server.tool()
async def list_runs(limit: int = 20) -> str:
    """List recent Aegis DQ run IDs, newest first."""
    run_ids = await list_run_ids(db_path=DB_PATH)
    return json.dumps(run_ids[:limit])


@mcp_server.tool()
async def get_trajectory(run_id: str) -> str:
    """Get the full decision trajectory for a completed run in ShareGPT format."""
    from ...audit.logger import get_decisions
    decisions = await get_decisions(run_id, db_path=DB_PATH)
    if not decisions:
        return json.dumps({"error": f"No decisions found for run_id={run_id!r}"})
    return json.dumps(decisions)


@mcp_server.tool()
async def get_run_report(run_id: str) -> str:
    """Get the ShareGPT-formatted trajectory for a run, including metadata."""
    data = await export_sharegpt(run_id, db_path=DB_PATH)
    return json.dumps(data)


@mcp_server.tool()
async def run_validation(
    rules_path: str,
    db_path: str = ":memory:",
    no_llm: bool = False,
) -> str:
    """Run Aegis DQ validation against a rules YAML file.

    Args:
        rules_path: Path to the rules YAML file.
        db_path: DuckDB database path (default: in-memory).
        no_llm: If True, skip LLM diagnosis and run offline.

    Returns:
        JSON-encoded validation report.
    """
    from ...adapters.warehouse.duckdb import DuckDBAdapter
    from ...core.agent import AegisAgent
    from ...rules.parser import load_rules

    rules = load_rules(Path(rules_path))
    warehouse = DuckDBAdapter(db_path)
    llm = None if no_llm else _default_llm()
    agent = AegisAgent(warehouse_adapter=warehouse, llm_adapter=llm)
    state = await agent.run(rules, triggered_by="mcp")
    return json.dumps(state["report"])


@mcp_server.tool()
async def search_decisions(query: str, run_id: str | None = None, limit: int = 20) -> str:
    """Full-text search over the audit decision trail.

    Args:
        query: Search terms (e.g. "null ETL bug", "root cause orders")
        run_id: Optional — restrict to a specific run
        limit: Maximum number of results to return

    Returns:
        JSON array of matching decision records.
    """
    from ...audit.search import search_decisions as _search
    results = await _search(query, db_path=DB_PATH, limit=limit, run_id=run_id)
    return json.dumps(results)


def _default_llm():
    """Return the default LLM adapter (Anthropic if key available, else None)."""
    import os
    if os.environ.get("ANTHROPIC_API_KEY"):
        from ...adapters.llm.anthropic import AnthropicAdapter
        return AnthropicAdapter()
    return None
