---
name: aegis-dq
description: Run agentic data quality validations across warehouses (DuckDB, BigQuery, Athena, Databricks, Postgres), inspect audit trails, and investigate failures with LLM diagnosis — all conversationally.
license: Apache-2.0
compatibility: Requires Python 3.11+ and aegis-dq installed (pip install aegis-dq). Supports macOS, Linux, Windows.
metadata:
  author: Aegis Contributors
  version: 0.7.0
  repository: https://github.com/aegis-dq/aegis-dq
  docs: https://aegis-dq.dev/integrations/hermes
  tags: data-quality sql warehouse analytics audit
required_environment_variables:
  - name: ANTHROPIC_API_KEY
    description: Anthropic API key for LLM diagnosis. Optional — omit to run offline (no_llm=true).
---

Aegis DQ runs structured data quality rules against your warehouses and uses LLMs to diagnose failures, trace root causes, and propose SQL remediations. Every decision is audit-logged.

## Setup

Install Aegis and start the MCP server:

```bash
pip install aegis-dq
aegis mcp serve
```

Set warehouse environment variables for any system you want to validate:

| Warehouse | Environment variables |
|---|---|
| DuckDB | `DUCKDB_PATH` (default: `:memory:`) |
| BigQuery | `BQ_PROJECT`, `BQ_DATASET` |
| Athena | `ATHENA_S3_STAGING_DIR`, `AWS_REGION` |
| Databricks | `DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_TOKEN` |
| Postgres / Redshift | `POSTGRES_DSN` |

## Available tools

- **`run_validation`** — Run a rules YAML file against a warehouse. Returns pass/fail per rule, LLM diagnosis, root cause, and remediation SQL.
- **`list_runs`** — List recent run IDs from the audit trail.
- **`get_run_report`** — Get the full report for a past run.
- **`get_trajectory`** — Get the node-by-node LLM decision log for a run.
- **`search_decisions`** — Full-text search across all past LLM decisions.

## Example prompts

- "Run my rules.yaml against BigQuery and tell me what failed."
- "Show me the last 10 validation runs."
- "What was the root cause in yesterday's run?"
- "Search the audit trail for anything about null order IDs."
- "Run rules.yaml against Athena offline — no LLM, just pass/fail."

## Running a validation

Pass `warehouse` and `connection_params` to `run_validation`:

```
warehouse: bigquery
connection_params: {"project": "my-project", "dataset": "analytics"}
```

Or rely on env vars and omit `connection_params` entirely.

Pass `no_llm: true` to skip LLM diagnosis for faster offline checks.

## Edge cases

- If `connection_params` is omitted, Aegis falls back to env vars. If required env vars are missing, the tool returns a clear error listing which variables to set.
- `no_llm: true` skips LLM calls entirely — useful when no API key is available or for fast schema-only checks.
- Rules that reference tables not present in the warehouse fail with a clear SQL error, not a silent pass.
