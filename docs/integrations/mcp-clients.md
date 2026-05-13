# MCP Clients

Aegis ships a standard [Model Context Protocol](https://modelcontextprotocol.io) server. Any MCP-compatible client can connect to it — not just Hermes. This page covers configuration for Claude Desktop, Cursor, and Cline.

---

## Claude Desktop

### 1. Install Aegis

```bash
pip install aegis-dq
```

### 2. Edit the Claude Desktop config

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "aegis": {
      "command": "aegis",
      "args": ["mcp", "serve"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

Add warehouse env vars inside the `env` block for any warehouse you want to reach:

```json
{
  "mcpServers": {
    "aegis": {
      "command": "aegis",
      "args": ["mcp", "serve"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "BQ_PROJECT": "my-project",
        "BQ_DATASET": "analytics"
      }
    }
  }
}
```

### 3. Restart Claude Desktop

The Aegis tools appear in the tool picker once the server connects. Try:

> Run my rules.yaml against BigQuery and tell me what failed.

---

## Cursor

### 1. Open MCP settings

In Cursor: **Settings → Features → MCP** (or `Cmd+Shift+P` → "MCP: Add Server").

### 2. Add Aegis as a stdio server

```json
{
  "mcpServers": {
    "aegis": {
      "command": "aegis",
      "args": ["mcp", "serve"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

### 3. Use in the Cursor chat

Once connected, Cursor's AI can call Aegis tools inline. Useful for:

- Validating a rules file you have open in the editor
- Searching the audit trail while debugging a pipeline
- Getting LLM diagnosis without leaving the IDE

---

## Cline

### 1. Open Cline MCP settings

In VS Code with Cline installed: open the Cline sidebar → **MCP Servers** tab → **Add Server**.

### 2. Add the server config

```json
{
  "aegis": {
    "command": "aegis",
    "args": ["mcp", "serve"],
    "env": {
      "ANTHROPIC_API_KEY": "sk-ant-..."
    }
  }
}
```

### 3. Use in Cline chat

Cline can now call Aegis tools mid-task. Example:

> Validate the rules in `rules/orders.yaml` against Postgres and show me the failures.

---

## HTTP / SSE transport (remote servers)

All examples above use **stdio transport** — the server runs as a local subprocess. For remote access (e.g. a shared team server), use SSE transport:

```bash
aegis mcp serve --transport sse --port 8765
```

Connect clients to `http://your-server:8765/sse`. Note: SSE transport does not encrypt traffic — run behind a reverse proxy with TLS for production use.

---

## Environment variables reference

Set these in the `env` block of your client config, or export them in your shell before starting the server.

### LLM

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (Claude). Used for LLM diagnosis. |
| `OPENAI_API_KEY` | OpenAI API key. |

### DuckDB

| Variable | Default | Description |
|---|---|---|
| `DUCKDB_PATH` | `:memory:` | Path to DuckDB database file. |

### BigQuery

| Variable | Description |
|---|---|
| `BQ_PROJECT` | GCP project ID |
| `BQ_DATASET` | Default dataset |
| `BQ_LOCATION` | BigQuery location (default: `US`) |
| `GOOGLE_CLOUD_PROJECT` | Fallback for `BQ_PROJECT` |

### Athena

| Variable | Description |
|---|---|
| `ATHENA_S3_STAGING_DIR` | S3 path for query result staging (e.g. `s3://bucket/athena/`) |
| `AWS_REGION` | AWS region (e.g. `us-east-1`) |
| `ATHENA_SCHEMA` | Default Glue/Athena database (default: `default`) |

### Databricks

| Variable | Description |
|---|---|
| `DATABRICKS_HOST` | Workspace hostname (e.g. `abc.azuredatabricks.net`) |
| `DATABRICKS_HTTP_PATH` | SQL warehouse HTTP path |
| `DATABRICKS_TOKEN` | Personal access token or service principal secret |

### Postgres / Redshift

| Variable | Description |
|---|---|
| `POSTGRES_DSN` | Full DSN (e.g. `postgresql://user:pass@host:5432/db`). Takes precedence over individual vars. |
| `PGHOST` | Hostname |
| `PGPORT` | Port (default: `5432`) |
| `PGDATABASE` | Database name |
| `PGUSER` | Username |
| `PGPASSWORD` | Password |

---

## Available tools

| Tool | Description |
|---|---|
| `run_validation` | Run a rules YAML file against a warehouse. Returns full JSON report with pass/fail, LLM diagnosis, root cause, and remediation SQL. |
| `list_runs` | List recent run IDs from the audit trail, newest first. |
| `get_run_report` | Get the full report for a past run by ID. |
| `get_trajectory` | Get the node-by-node LLM decision log for a run. |
| `search_decisions` | Full-text search across all past LLM decisions. |

---

## See also

- [Hermes integration](hermes.md) — Hermes-specific setup with scheduling and alerting
- [MCP Server reference](mcp.md) — tool parameter details
