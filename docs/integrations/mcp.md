# MCP Server

Aegis ships a [Model Context Protocol](https://modelcontextprotocol.io) server that exposes five tools to any MCP-compatible client. Connect Claude Desktop, Cursor, Cline, Hermes, or any other MCP client and run data quality validations conversationally.

---

## Start the server

```bash
aegis mcp serve
```

The server uses **stdio transport** by default — it runs as a subprocess managed by your MCP client. For remote access, use SSE:

```bash
aegis mcp serve --transport sse --port 8765
```

---

## Tools

### `run_validation`

Run a rules YAML file against a warehouse. Returns a JSON report with pass/fail per rule, LLM diagnosis, root cause analysis, and remediation SQL.

**Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `rules_path` | string | required | Path to the rules YAML file |
| `warehouse` | string | `"duckdb"` | Warehouse type: `duckdb`, `bigquery`, `athena`, `databricks`, `postgres` |
| `connection_params` | string (JSON) | `"{}"` | Warehouse connection kwargs as a JSON object. Falls back to environment variables if omitted. |
| `no_llm` | bool | `false` | Skip LLM diagnosis. Returns rule pass/fail only. |

**Examples**

=== "DuckDB"
    ```json
    {
      "rules_path": "/home/user/rules/orders.yaml",
      "warehouse": "duckdb",
      "connection_params": "{\"path\": \"/data/prod.duckdb\"}"
    }
    ```

=== "BigQuery"
    ```json
    {
      "rules_path": "/home/user/rules/orders.yaml",
      "warehouse": "bigquery",
      "connection_params": "{\"project\": \"my-project\", \"dataset\": \"analytics\"}"
    }
    ```

=== "Athena"
    ```json
    {
      "rules_path": "/home/user/rules/orders.yaml",
      "warehouse": "athena",
      "connection_params": "{\"s3_staging_dir\": \"s3://bucket/athena/\", \"region_name\": \"us-east-1\"}"
    }
    ```

=== "Databricks"
    ```json
    {
      "rules_path": "/home/user/rules/orders.yaml",
      "warehouse": "databricks",
      "connection_params": "{\"server_hostname\": \"abc.azuredatabricks.net\", \"http_path\": \"/sql/1.0/warehouses/abc\", \"access_token\": \"dapi...\"}"
    }
    ```

=== "Postgres"
    ```json
    {
      "rules_path": "/home/user/rules/orders.yaml",
      "warehouse": "postgres",
      "connection_params": "{\"dsn\": \"postgresql://user:pass@host:5432/db\"}"
    }
    ```

**Using environment variables instead**

Set warehouse env vars in your client config (see [MCP Clients](mcp-clients.md)) and omit `connection_params`. Aegis picks them up automatically:

```json
{ "rules_path": "/home/user/rules/orders.yaml", "warehouse": "bigquery" }
```

---

### `list_runs`

List recent run IDs from the audit trail, newest first.

**Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | int | `20` | Maximum number of run IDs to return |

**Returns**: JSON array of run ID strings.

---

### `get_run_report`

Get the full report for a past validation run.

**Parameters**

| Parameter | Type | Description |
|---|---|---|
| `run_id` | string | Run ID from `list_runs` |

**Returns**: JSON object with `run_id`, `summary`, `failures`, and metadata.

---

### `get_trajectory`

Get the node-by-node LLM decision log for a run — every prompt, response, cost, and latency. Useful for auditing exactly what Aegis decided and why.

**Parameters**

| Parameter | Type | Description |
|---|---|---|
| `run_id` | string | Run ID from `list_runs` |

**Returns**: JSON array of decision records, one per agent node that made an LLM call.

---

### `search_decisions`

Full-text search across all LLM decisions in the audit trail.

**Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | string | required | Search terms (e.g. `"null order_id"`, `"root cause ETL"`) |
| `run_id` | string | `null` | Restrict search to a specific run |
| `limit` | int | `20` | Maximum results |

**Returns**: JSON array of matching decision records with run ID, step, and summary.

---

## Example client prompts

```
Run /home/user/rules/orders.yaml against BigQuery and summarise the failures.
```

```
Show me the last 5 validation runs.
```

```
What did Aegis diagnose for run run_20260513_143022_a1b2c3?
```

```
Search the audit trail for anything about null order IDs.
```

```
Run my rules against Athena offline — no LLM, just tell me what passes and fails.
```

---

## Client setup guides

- [Hermes](hermes.md)
- [Claude Desktop, Cursor, Cline](mcp-clients.md)
