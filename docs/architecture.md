# Architecture

Aegis is a LangGraph-orchestrated agent that runs a deterministic 7-node pipeline. Each node is a discrete step with a defined input state and output state. Nodes that call an LLM are skippable (`--no-llm`) without affecting the others.

---

## The 7-node pipeline

```
rules.yaml
    │
    ▼
  plan ──► execute ──► reconcile ──► classify ──► diagnose ──► rca ──► report
```

### 1. plan

Reads `rules.yaml`, validates each rule against the schema, groups rules by warehouse, and produces an **execution plan** — an ordered list of (warehouse, rule) pairs. Rules targeting the same warehouse are batched to reuse a single connection. Rules with `depends_on` are topologically sorted.

### 2. execute

Runs each rule against its warehouse adapter using the appropriate SQL template for that rule type. Supports all 28 rule types. Returns a list of **check results**, each containing: `passed` (bool), `rows_failed`, `rows_checked`, `failed_sample` (up to 20 sample rows), and `execution_ms`.

### 3. reconcile

Handles **reconciliation rules** that compare a source table to a target table (e.g. row counts match, checksum matches). Runs source and target queries in parallel and computes the delta. Non-reconciliation rules pass through this node unchanged.

### 4. classify

Assigns or upgrades severity for each failure using a heuristic + optional LLM triage. A failure affecting more than 5% of rows in a critical table is automatically escalated. The **blast radius** (estimated downstream table count from the lineage graph) is factored into the final severity score. This node does not require an LLM — heuristics run even in `--no-llm` mode.

### 5. diagnose

For each failed check, calls the configured LLM with a structured prompt containing: the rule definition, the check result, the failed sample rows, and any `common_causes` from the rule's `diagnosis` block. Returns a plain-English **explanation**, **likely cause**, and **recommended action** for each failure.

### 6. rca

Performs **root cause analysis** using the OpenLineage lineage graph to trace a failed table upstream. Calls the LLM with the lineage path to identify which upstream dataset, job, or transformation introduced the issue. Produces a lineage-annotated root cause string that is included in the final report.

### 7. report

Assembles the final JSON report: run metadata, severity breakdown, per-rule results with LLM diagnosis and RCA, total LLM cost, and run duration. Writes the report to stdout (table + diagnosis text via Rich), to `--output-json` if specified, and to the audit trail.

---

## Adapters

Aegis uses a two-tier adapter pattern — one tier for LLMs, one for warehouses. Adapters are thin protocol implementations; the pipeline nodes never call a warehouse or LLM directly.

```
LLM adapters
─────────────────────────────────────────────────
  Anthropic   claude-haiku-4-5 (default)
              claude-sonnet-4-5
              claude-opus-4-5

  OpenAI      gpt-4o-mini (default)
              gpt-4o

  Ollama      any locally-pulled model
              (llama3.2, mistral, phi3, etc.)
              runs on http://localhost:11434

Warehouse adapters
─────────────────────────────────────────────────
  DuckDB      local file or in-memory
  BigQuery    project + dataset via service account
  Databricks  cluster or SQL warehouse via token
  Athena      S3 + Glue catalog via IAM role
```

Implementing a new warehouse adapter requires a single Python class with three methods: `connect()`, `execute_scalar(sql)`, and `execute_sample(sql, limit)`.

---

## Audit trail

Every LLM call made during a run is recorded in `~/.aegis/history.db` (SQLite). The schema has two tables:

- **runs** — one row per `aegis run` invocation: `run_id`, `started_at`, `rules_file`, `warehouse`, `llm`, `total_cost_usd`, `summary_json`
- **decisions** — one row per LLM call: `run_id`, `node` (diagnose / rca / classify), `rule_id`, `prompt`, `response`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`

The `decisions` table has an FTS5 virtual table on `(prompt, response)`, enabling full-text search:

```bash
aegis audit search "null order_id"
aegis audit search "currency conversion"
```

### ShareGPT export for fine-tuning

```bash
aegis audit export-dataset output.jsonl
```

Each entry in the JSONL file is a ShareGPT-format conversation: the system prompt, the user turn (rule context + failed rows), and the assistant turn (the actual LLM diagnosis). This format is directly compatible with fine-tuning pipelines for most open-source models.

---

## Integrations

### Airflow

The `AegisOperator` wraps an `aegis run` invocation as a native Airflow task. See [Airflow Integration](integrations/airflow.md).

### dbt

`aegis dbt generate manifest.json` reads a dbt `manifest.json` and emits Aegis rules for every `not_null`, `unique`, `accepted_values`, and `relationships` test found in the manifest. See [dbt Integration](integrations/dbt.md).

### MCP server

Aegis ships a Model Context Protocol server that exposes five tools to Claude Desktop (or any MCP-compatible client):

| Tool | Description |
|---|---|
| `aegis_run` | Run a rules file against a warehouse and return the report |
| `aegis_validate` | Validate a rules file offline and return any errors |
| `aegis_list_runs` | List recent runs from the audit trail |
| `aegis_trajectory` | Return the full node trajectory for a given run ID |
| `aegis_search` | Full-text search the audit trail |

See [MCP Server](integrations/mcp.md) for the Claude Desktop configuration.
