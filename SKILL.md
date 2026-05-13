# Aegis DQ — Hermes Skill

**Skill ID**: `aegis-dq`
**Version**: `0.7.0`
**Author**: Aegis Contributors
**License**: Apache 2.0
**Repository**: https://github.com/aegis-dq/aegis-dq

---

## What this skill does

Aegis DQ is an agentic data quality framework. This skill connects Hermes to a locally-running Aegis MCP server, giving you conversational access to:

- **Run data quality validations** across any warehouse (DuckDB, BigQuery, Athena, Databricks, Postgres)
- **Inspect audit trails** — every LLM diagnosis, root cause analysis, and remediation decision is logged and searchable
- **Investigate failures** — retrieve full node-by-node trajectories showing exactly what Aegis decided and why

---

## Prerequisites

1. Install Aegis:
   ```bash
   pip install aegis-dq
   ```

2. Start the MCP server:
   ```bash
   aegis mcp serve
   ```

3. Configure Hermes to connect to the server (see Configuration below).

---

## Configuration

Add to your Hermes skills config:

```yaml
skills:
  - id: aegis-dq
    transport: stdio
    command: aegis
    args: [mcp, serve]
    env:
      ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"   # for LLM diagnosis
      # Warehouse env vars (set whichever you use):
      # DUCKDB_PATH: /path/to/prod.duckdb
      # BQ_PROJECT: my-gcp-project
      # BQ_DATASET: analytics
      # ATHENA_S3_STAGING_DIR: s3://my-bucket/athena/
      # AWS_REGION: us-east-1
      # DATABRICKS_HOST: abc.azuredatabricks.net
      # DATABRICKS_HTTP_PATH: /sql/1.0/warehouses/abc
      # DATABRICKS_TOKEN: dapi...
      # POSTGRES_DSN: postgresql://user:pass@host:5432/db
```

---

## Tools

| Tool | Description |
|---|---|
| `run_validation` | Run a rules YAML file against any supported warehouse. Returns a full JSON report with pass/fail per rule, LLM diagnosis, root cause, and remediation SQL. |
| `list_runs` | List recent validation run IDs from the audit trail. |
| `get_run_report` | Retrieve the full report for a past run by ID. |
| `get_trajectory` | Get the node-by-node LLM decision log for a run — every prompt, response, cost, and latency. |
| `search_decisions` | Full-text search across all past LLM decisions in the audit trail. |

---

## Example prompts

```
Run my rules.yaml against my Athena warehouse and tell me what failed.
```

```
Show me the last 10 validation runs.
```

```
What was the root cause in yesterday's run?
```

```
Search the audit trail for anything related to null order IDs.
```

```
Run rules.yaml against BigQuery project my-project, dataset analytics, and give me a summary.
```

```
Show me the full diagnosis trace for run run_20260513_143022_a1b2c3.
```

---

## Warehouses

Pass the `warehouse` and `connection_params` arguments to `run_validation`:

| Warehouse | Example connection_params |
|---|---|
| DuckDB | `{"path": "/data/prod.duckdb"}` |
| BigQuery | `{"project": "my-project", "dataset": "analytics"}` |
| Athena | `{"s3_staging_dir": "s3://bucket/athena/", "region_name": "us-east-1"}` |
| Databricks | `{"server_hostname": "abc.azuredatabricks.net", "http_path": "/sql/1.0/warehouses/abc", "access_token": "dapi..."}` |
| Postgres | `{"dsn": "postgresql://user:pass@host:5432/db"}` |

Connection params can also be set via environment variables — see the Configuration section above.

---

## Offline mode

Pass `no_llm: true` to `run_validation` to skip LLM diagnosis and run rule checks only. Useful for fast checks or when no API key is configured.

---

## Links

- Docs: https://aegis-dq.dev/integrations/hermes
- MCP reference: https://aegis-dq.dev/integrations/mcp-clients
- GitHub: https://github.com/aegis-dq/aegis-dq
- PyPI: https://pypi.org/project/aegis-dq/
