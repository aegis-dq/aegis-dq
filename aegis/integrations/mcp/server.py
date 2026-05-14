"""Aegis MCP server — exposes Aegis DQ tools via the Model Context Protocol."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ...audit.trajectory import export_sharegpt, list_run_ids
from ...memory.store import DB_PATH

mcp_server = FastMCP(
    "aegis-dq",
    instructions=(
        "Aegis DQ — agentic data quality framework. "
        "Use these tools to run validations, inspect audit trails, and analyze failures."
    ),
)


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
    warehouse: str = "duckdb",
    connection_params: str = "{}",
    no_llm: bool = False,
) -> str:
    """Run Aegis DQ validation against a rules YAML file.

    Args:
        rules_path: Path to the rules YAML file.
        warehouse: Warehouse type — one of: duckdb, bigquery, athena, databricks, postgres.
            Defaults to "duckdb" (in-memory). Set env vars for connection defaults
            (e.g. BQ_PROJECT + BQ_DATASET for BigQuery, POSTGRES_DSN for Postgres).
        connection_params: JSON object with warehouse connection kwargs. Overrides env
            var defaults. Examples:
              duckdb:     {"path": "/data/prod.duckdb"}
              bigquery:   {"project": "my-proj", "dataset": "analytics"}
              athena:     {"s3_staging_dir": "s3://bucket/athena/", "region_name": "us-east-1"}
              databricks: {"server_hostname": "abc.azuredatabricks.net",
                           "http_path": "/sql/1.0/warehouses/abc", "access_token": "dapi..."}
              postgres:   {"dsn": "postgresql://user:pass@host:5432/db"}
        no_llm: If True, skip LLM diagnosis and run offline.

    Returns:
        JSON-encoded validation report.
    """
    from ...adapters.warehouse.factory import build_adapter
    from ...core.agent import AegisAgent
    from ...rules.parser import load_rules

    rules = load_rules(Path(rules_path))
    warehouse_adapter = build_adapter(warehouse, connection_params)
    llm = None if no_llm else _default_llm()
    agent = AegisAgent(warehouse_adapter=warehouse_adapter, llm_adapter=llm)
    state = await agent.run(rules, triggered_by="mcp")
    return json.dumps(state["report"])


@mcp_server.tool()
async def load_pipeline(manifest_path: str) -> str:
    """Load a pipeline manifest and return its configuration + goal as context.

    Use this before run_validation to understand what a named pipeline does.
    After calling this, call run_validation with the rules_path and connection_params
    from the returned manifest.

    Args:
        manifest_path: Path to a pipeline.yaml manifest file.

    Returns:
        JSON with the pipeline config and a ready-to-use run_validation call.
    """
    from ...pipeline.manifest import PipelineManifest

    path = Path(manifest_path)
    if not path.exists():
        return json.dumps({"error": f"Manifest not found: {manifest_path}"})

    m = PipelineManifest.load(path)
    return json.dumps(
        {
            "name": m.name,
            "description": m.description,
            "goal": m.goal,
            "rules_path": m.rules,
            "warehouse": m.warehouse.type,
            "connection_params": m.warehouse.connection,
            "llm_provider": m.llm.provider,
            "llm_model": m.llm.model,
            "kb": m.kb,
            "run_validation_call": {
                "rules_path": m.rules,
                "warehouse": m.warehouse.type,
                "connection_params": m.connection_params_json(),
            },
        }
    )


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
