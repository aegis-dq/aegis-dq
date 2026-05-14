"""Aegis MCP server — exposes Aegis DQ tools via the Model Context Protocol."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from ...audit.trajectory import export_sharegpt, list_run_ids
from ...memory.store import DB_PATH, _connect

mcp_server = FastMCP(
    "aegis-dq",
    instructions=(
        "Aegis DQ — agentic data quality framework. "
        "Use these tools to run validations, inspect audit trails, and analyze failures."
    ),
)


@mcp_server.tool()
async def list_runs(
    limit: Annotated[int, "Maximum number of run IDs to return (default: 20)"] = 20,
) -> str:
    """List recent Aegis DQ run IDs from the audit trail, newest first.

    Use this to discover available run IDs before calling get_run_report,
    get_trajectory, compare_reports, summarize_reports, or check_consistency.

    Returns:
        JSON array of run ID strings, ordered newest to oldest.
    """
    run_ids = await list_run_ids(db_path=DB_PATH)
    return json.dumps(run_ids[:limit])


@mcp_server.tool()
async def get_trajectory(
    run_id: Annotated[str, "The run ID to retrieve — use list_runs to get available IDs"],
) -> str:
    """Get the node-by-node LLM decision log for a completed run.

    Returns every prompt sent and response received during the validation —
    the full reasoning chain across classify, diagnose, root-cause, and
    remediation nodes. Use this to audit AI decisions, debug unexpected
    diagnoses, or trace exactly why a rule was flagged as failing.

    Args:
        run_id: The run ID to retrieve (from list_runs).

    Returns:
        JSON array of decision records, each with node_name, prompt,
        response, cost_usd, and latency_ms.
    """
    from ...audit.logger import get_decisions

    decisions = await get_decisions(run_id, db_path=DB_PATH)
    if not decisions:
        return json.dumps({"error": f"No decisions found for run_id={run_id!r}"})
    return json.dumps(decisions)


@mcp_server.tool()
async def get_run_report(
    run_id: Annotated[str, "The run ID to retrieve — use list_runs to get available IDs"],
) -> str:
    """Get the full validation report for a completed run by ID.

    Returns the complete report including pass/fail status for every rule,
    LLM diagnosis, root cause analysis, SQL remediation proposals, severity
    breakdown, and cost/latency summary. Use list_runs to discover run IDs.

    Args:
        run_id: The run ID to retrieve (from list_runs).

    Returns:
        JSON object with summary, failures (each with diagnosis, root_cause,
        remediation_sql, severity), and cost_usd.
    """
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


async def _load_report(run_id: str) -> dict | None:
    """Load a full report from the runs table by run_id. Returns None if not found."""
    if not DB_PATH.exists():
        return None
    async with _connect(DB_PATH) as db:
        cursor = await db.execute("SELECT report_json FROM runs WHERE run_id = ?", (run_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row[0])


@mcp_server.tool()
async def compare_reports(run_id_a: str, run_id_b: str) -> str:
    """Compare two validation runs side by side.

    Shows regressions (rules that newly failed), fixes (rules that stopped failing),
    persistent failures, and summary deltas (pass rate, cost).

    Args:
        run_id_a: The baseline run ID.
        run_id_b: The comparison run ID.

    Returns:
        JSON with regressions, fixes, persistent_failures, and summary_delta.
    """
    report_a = await _load_report(run_id_a)
    report_b = await _load_report(run_id_b)

    if report_a is None:
        return json.dumps({"error": f"Run not found: {run_id_a!r}"})
    if report_b is None:
        return json.dumps({"error": f"Run not found: {run_id_b!r}"})

    failed_a = {f["rule_id"] for f in report_a.get("failures", [])}
    failed_b = {f["rule_id"] for f in report_b.get("failures", [])}

    sum_a = report_a.get("summary", {})
    sum_b = report_b.get("summary", {})

    return json.dumps(
        {
            "run_a": run_id_a,
            "run_b": run_id_b,
            "summary_a": sum_a,
            "summary_b": sum_b,
            "summary_delta": {
                "pass_rate": round(sum_b.get("pass_rate", 0.0) - sum_a.get("pass_rate", 0.0), 1),
                "failed_delta": sum_b.get("failed", 0) - sum_a.get("failed", 0),
                "cost_delta_usd": round(
                    report_b.get("cost_usd", 0.0) - report_a.get("cost_usd", 0.0), 6
                ),
            },
            "regressions": sorted(failed_b - failed_a),
            "fixes": sorted(failed_a - failed_b),
            "persistent_failures": sorted(failed_a & failed_b),
        }
    )


@mcp_server.tool()
async def summarize_reports(run_ids: list[str]) -> str:
    """Summarize one or more validation runs.

    Returns pass rate, severity breakdown, top failures, and cost for each run.
    Useful for a quick multi-run overview without loading full reports.

    Args:
        run_ids: List of run IDs to summarize.

    Returns:
        JSON array of per-run summaries plus a total count.
    """
    summaries = []
    for run_id in run_ids:
        report = await _load_report(run_id)
        if report is None:
            summaries.append({"run_id": run_id, "error": "not found"})
            continue
        s = report.get("summary", {})
        top_failures = [
            {
                "rule_id": f["rule_id"],
                "table": f["table"],
                "severity": f.get("effective_severity", f.get("severity")),
            }
            for f in report.get("failures", [])[:5]
        ]
        summaries.append(
            {
                "run_id": run_id,
                "timestamp": report.get("timestamp"),
                "triggered_by": report.get("triggered_by"),
                "total_rules": s.get("total_rules"),
                "passed": s.get("passed"),
                "failed": s.get("failed"),
                "pass_rate": s.get("pass_rate"),
                "severity_breakdown": s.get("severity_breakdown", {}),
                "cost_usd": report.get("cost_usd"),
                "top_failures": top_failures,
            }
        )
    return json.dumps({"total": len(summaries), "runs": summaries})


@mcp_server.tool()
async def check_consistency(run_id_a: str, run_id_b: str) -> str:
    """Check consistency between two validation runs.

    Identifies flapping rules (different pass/fail status between runs) and
    rule-set drift (different number of rules evaluated). Returns a consistency
    score so you can tell at a glance whether the two runs agree.

    Args:
        run_id_a: First run ID.
        run_id_b: Second run ID.

    Returns:
        JSON with flapping_rules, consistent_failures, consistency_score_pct,
        and rule_set_changed flag.
    """
    report_a = await _load_report(run_id_a)
    report_b = await _load_report(run_id_b)

    if report_a is None:
        return json.dumps({"error": f"Run not found: {run_id_a!r}"})
    if report_b is None:
        return json.dumps({"error": f"Run not found: {run_id_b!r}"})

    failed_a = {f["rule_id"] for f in report_a.get("failures", [])}
    failed_b = {f["rule_id"] for f in report_b.get("failures", [])}

    all_failing = failed_a | failed_b
    consistent_failures = sorted(failed_a & failed_b)
    flapping = sorted(all_failing - (failed_a & failed_b))

    sum_a = report_a.get("summary", {})
    sum_b = report_b.get("summary", {})
    total_a = sum_a.get("total_rules", 0)
    total_b = sum_b.get("total_rules", 0)

    if all_failing:
        consistency_score = round(len(consistent_failures) / len(all_failing) * 100, 1)
    else:
        consistency_score = 100.0

    return json.dumps(
        {
            "run_a": run_id_a,
            "run_b": run_id_b,
            "consistent": len(flapping) == 0 and total_a == total_b,
            "consistency_score_pct": consistency_score,
            "flapping_rules": flapping,
            "consistent_failures": consistent_failures,
            "rule_set_changed": total_a != total_b,
            "total_rules_a": total_a,
            "total_rules_b": total_b,
        }
    )


def _default_llm():
    """Return the default LLM adapter based on available env vars, else None.

    Priority: ANTHROPIC_API_KEY → OPENAI_API_KEY → AWS_DEFAULT_REGION (Bedrock).
    Set AEGIS_LLM_PROVIDER to override (anthropic|openai|bedrock).
    """
    import os

    from ...adapters.llm.retry import RetryingLLMAdapter

    provider = os.environ.get("AEGIS_LLM_PROVIDER", "").lower()

    if provider == "bedrock" or (not provider and os.environ.get("AWS_DEFAULT_REGION")):
        try:
            from ...adapters.llm.bedrock import BedrockAdapter

            model = os.environ.get("AEGIS_LLM_MODEL") or None
            kwargs = {}
            if model:
                kwargs["model"] = model
            return RetryingLLMAdapter(BedrockAdapter(**kwargs))
        except ImportError:
            pass

    if provider == "openai" or (not provider and os.environ.get("OPENAI_API_KEY")):
        try:
            from ...adapters.llm.openai import OpenAIAdapter

            model = os.environ.get("AEGIS_LLM_MODEL") or None
            return RetryingLLMAdapter(OpenAIAdapter(**({"model": model} if model else {})))
        except ImportError:
            pass

    if os.environ.get("ANTHROPIC_API_KEY") or provider == "anthropic":
        from ...adapters.llm.anthropic import AnthropicAdapter

        model = os.environ.get("AEGIS_LLM_MODEL") or None
        return RetryingLLMAdapter(AnthropicAdapter(**({"model": model} if model else {})))

    return None
