# Hermes Integration

Aegis DQ integrates with [Hermes](https://github.com/nousresearch/hermes-agent) via the Model Context Protocol (MCP). Once configured, Hermes can run data quality validations, inspect audit trails, and investigate failures conversationally — across any of your connected warehouses.

---

## How it works

```
You (Hermes chat)
      │
      ▼
  Hermes agent
      │  MCP stdio
      ▼
  Aegis MCP server  ──►  Warehouse (Athena / BigQuery / Databricks / Postgres / DuckDB)
      │
      ▼
  LLM diagnosis + audit log
```

Hermes calls Aegis tools via MCP. Aegis runs your rules against the warehouse, logs every LLM decision, and returns a structured report. Hermes can then reason over the results, remember past runs, and schedule future checks.

---

## Setup

### 1. Install Aegis

```bash
pip install aegis-dq
```

### 2. Verify the MCP server starts

```bash
aegis mcp serve
```

You should see no errors. Press `Ctrl+C` to stop.

### 3. Configure Hermes

Add Aegis to your Hermes skills configuration:

```yaml
skills:
  - id: aegis-dq
    transport: stdio
    command: aegis
    args: [mcp, serve]
    env:
      ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"
```

Add warehouse environment variables for any system you want to validate:

=== "BigQuery"
    ```yaml
    env:
      BQ_PROJECT: my-gcp-project
      BQ_DATASET: analytics
    ```

=== "Athena"
    ```yaml
    env:
      ATHENA_S3_STAGING_DIR: s3://my-bucket/athena/
      AWS_REGION: us-east-1
    ```

=== "Databricks"
    ```yaml
    env:
      DATABRICKS_HOST: abc.azuredatabricks.net
      DATABRICKS_HTTP_PATH: /sql/1.0/warehouses/abc
      DATABRICKS_TOKEN: dapi...
    ```

=== "Postgres / Redshift"
    ```yaml
    env:
      POSTGRES_DSN: postgresql://user:pass@host:5432/db
    ```

=== "DuckDB"
    ```yaml
    env:
      DUCKDB_PATH: /data/prod.duckdb
    ```

---

## Example conversations

### Run a validation

> **You**: Run my rules.yaml against the Athena warehouse and tell me what failed.

Hermes calls `run_validation` with `warehouse=athena` and your configured env vars. Aegis runs every rule, produces an LLM diagnosis for each failure, and returns a structured report. Hermes summarises it in plain language.

### Investigate a failure

> **You**: What was the root cause of the order_value failures in yesterday's run?

Hermes calls `list_runs` to find the run ID, then `get_trajectory` to retrieve the full node-by-node decision log — including the root cause analysis LLM produced, the evidence it used, and the remediation SQL it suggested.

### Search past decisions

> **You**: Have we ever seen null order IDs before?

Hermes calls `search_decisions` with a full-text query. Aegis searches across all past LLM diagnoses, returning every run where null order IDs appeared in the reasoning.

### Offline check

> **You**: Quickly validate my rules.yaml without hitting any warehouse.

Pass `no_llm=true` and `warehouse=duckdb` with an in-memory path. Aegis validates the rule schema and runs checks against no data.

---

## Available tools

| Tool | What Hermes can ask |
|---|---|
| `run_validation` | "Run my rules against BigQuery" |
| `list_runs` | "Show me recent validation runs" |
| `get_run_report` | "Give me the report for run XYZ" |
| `get_trajectory` | "Show me exactly what Aegis decided for run XYZ" |
| `search_decisions` | "Search audit trail for null values" |

---

## Scheduling with Hermes

Hermes can schedule Aegis validations on a recurring cadence:

> **You**: Run my rules.yaml every morning at 8am and alert me if anything fails.

Hermes handles the scheduling and alerting layer. Aegis handles the validation and diagnosis. Each run is automatically logged to the audit trail.

---

## Troubleshooting

**Hermes can't connect to Aegis**
: Run `aegis mcp serve` manually and check for import errors. Ensure `aegis-dq` is installed in the same Python environment Hermes uses.

**"Missing required connection params" error**
: The warehouse env vars aren't set. Check your Hermes skills config `env` block.

**LLM diagnosis is slow**
: Pass `no_llm=true` for a fast offline check. LLM diagnosis is opt-in.

**Validation runs but returns no failures**
: Check that `rules_path` points to the correct file and that the `table` field in your rules matches the actual table name in the warehouse.

---

## See also

- [MCP Clients](mcp-clients.md) — Claude Desktop, Cursor, Cline configuration
- [MCP Server reference](mcp.md) — full tool documentation
- [Rule Schema Reference](../rule-schema-reference.md) — how to write rules
