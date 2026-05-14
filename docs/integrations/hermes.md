# Hermes Integration

Aegis DQ integrates with [Hermes](https://github.com/nousresearch/hermes-agent) via the Model Context Protocol (MCP). Once configured, Hermes can generate rules from your policy docs, run validations, diagnose failures, and schedule recurring checks — across any connected warehouse — with a single conversational prompt.

---

## How it works

```
You (Hermes chat)
      │
      ▼
  Hermes agent  ──  memory / scheduling / multi-channel delivery
      │
      │  MCP stdio
      ▼
  Aegis MCP server
      │
      ├──► Warehouse  (DuckDB / BigQuery / Athena / Databricks / Postgres)
      ├──► LLM        (Anthropic / OpenAI / Ollama)
      └──► Audit log  (every decision, cost, and latency stored)
```

Hermes calls Aegis tools via MCP. Aegis runs your rules, logs every LLM decision, and returns a structured report. Hermes reasons over the results, remembers past runs, and can schedule future checks.

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

No errors means it's ready. Press `Ctrl+C` to stop.

### 3. Configure Hermes

Add Aegis to `~/.hermes/config.yaml`:

```yaml
model:
  default: claude-haiku-4-5-20251001   # or any model your provider supports
  provider: anthropic
  base_url: https://api.anthropic.com

mcp_servers:
  aegis:
    command: aegis
    args: [mcp, serve]
    env:
      DUCKDB_PATH: /data/prod.duckdb          # default DB for DuckDB runs
      ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"
```

Add warehouse environment variables for any system you want to validate:

=== "BigQuery"
    ```yaml
    env:
      BQ_PROJECT: my-gcp-project
      BQ_DATASET: analytics
      GOOGLE_APPLICATION_CREDENTIALS: /path/to/sa.json
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

### 4. Add your API key

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." >> ~/.hermes/.env
```

---

## Pipeline manifests — define once, run forever

The best way to use Aegis with Hermes is a **pipeline manifest**: a single YAML file that captures your database path, rules file, knowledge-base docs, and goal. Define it once; invoke it with two words.

### Create a manifest

```yaml
# my-project/pipeline.yaml
name: orders-dq
description: Daily order data quality checks — commerce platform

database: /data/prod.duckdb
rules: rules/orders.yaml

llm:
  provider: anthropic
  model: claude-haiku-4-5-20251001

kb:
  - docs/policy.md      # business rules / SLAs
  - docs/schema.md      # table definitions

output_json: reports/latest.json

goal: |
  Run all order data quality rules. For every failure explain the
  business impact, the likely root cause, and a concrete remediation
  step. Group findings by severity.
```

All paths in the manifest are resolved relative to the manifest file itself, so the manifest is portable.

### Run it from Hermes

```
Load the pipeline at my-project/pipeline.yaml and run it.
```

Hermes calls `load_pipeline` → reads the manifest → calls `run_validation` with the right params → diagnoses everything. You never re-explain the context.

### Or run it directly from the CLI

```bash
# Run the pipeline
aegis pipeline run my-project/pipeline.yaml

# Inspect without running
aegis pipeline show my-project/pipeline.yaml
```

### Manifest reference

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Pipeline identifier |
| `description` | string | no | Human-readable description |
| `database` | string | yes* | Path to DuckDB file (sugar for `warehouse.connection.path`) |
| `rules` | string | yes | Path to rules YAML file |
| `warehouse.type` | string | no | Warehouse type: `duckdb`, `bigquery`, `athena`, `databricks`, `postgres`. Default: `duckdb` |
| `warehouse.connection` | object | no | Warehouse connection kwargs (see [MCP Server reference](mcp.md)) |
| `llm.provider` | string | no | LLM provider. Default: `anthropic` |
| `llm.model` | string | no | Model override. Default: provider default |
| `kb` | list[string] | no | Knowledge-base files passed to `aegis generate` |
| `output_json` | string | no | Path to write the JSON report |
| `goal` | string | no | Instructions injected into Hermes context via `load_pipeline` |

---

## Generating rules from policy docs

Before running validation, Aegis can **generate rules directly from your business policy documents** — no hand-writing required.

### Via Hermes

```
Read docs/policy.md and docs/schema.md, then generate rules for the
transactions table against /data/prod.duckdb and save them to
rules/transactions.yaml.
```

### Via CLI

```bash
aegis generate transactions \
  --db /data/prod.duckdb \
  --kb docs/policy.md \
  --kb docs/schema.md \
  --output rules/transactions.yaml \
  --max-rules 15
```

Multiple `--kb` flags are supported — Aegis combines all context before calling the LLM. The generator produces `not_null`, `accepted_values`, `sql_expression`, and `custom_sql` checks (including CTEs, window functions, and multi-table JOINs) appropriate to your policies.

---

## Example conversations

### Run a named pipeline

```
Load the pipeline at demo/fraud/pipeline.yaml and run it.
```

### Generate rules then validate

```
Read demo/fraud/policy.md and demo/fraud/schema.md, generate rules for
all 6 tables against /tmp/fraud.duckdb, then run validation and give me
an AML compliance report grouped by severity.
```

### Investigate a specific failure

```
What was the root cause of the CTR filing failures in yesterday's run?
```

Hermes calls `list_runs` → `get_trajectory` → surfaces the full LLM reasoning chain.

### Search the audit trail

```
Have we ever seen OFAC sanction hits before?
```

Hermes calls `search_decisions` with a full-text query across all past diagnoses.

### Offline fast check

```
Run rules/orders.yaml against DuckDB without LLM — just pass/fail.
```

---

## Available MCP tools

| Tool | What it does |
|---|---|
| `load_pipeline` | Load a `pipeline.yaml` manifest — returns connection params and goal as context |
| `run_validation` | Run a rules YAML against any warehouse with LLM diagnosis |
| `list_runs` | List recent validation run IDs from the audit trail |
| `get_run_report` | Retrieve the full report for a past run |
| `get_trajectory` | Get the node-by-node LLM decision log for a run |
| `search_decisions` | Full-text search across all past LLM diagnoses |

---

## Real-world demo: AML / fraud detection

This walkthrough runs the full pipeline on a synthetic FinCore Bank dataset with deliberate fraud patterns seeded across 6 tables — covering CTR filing, structuring, OFAC sanctions, PEP oversight, velocity breach, dormant account reactivation, and geographic mismatch.

**1. Seed the database**

```bash
python3 -c "
import duckdb
conn = duckdb.connect('/tmp/fraud.duckdb')
conn.execute(open('demo/fraud/seed.sql').read())
conn.close()
"
```

**2. Generate rules from policy docs**

```bash
for table in transactions accounts customers counterparties compliance_flags sanctions_list; do
  aegis generate $table \
    --db /tmp/fraud.duckdb \
    --kb demo/fraud/policy.md \
    --kb demo/fraud/schema.md \
    --output demo/fraud/rules_${table}.yaml \
    --max-rules 15
done
```

**3. Run via the pipeline manifest**

```bash
aegis pipeline run demo/fraud/pipeline.yaml
```

**Expected output — 11 violations across 4 severity tiers:**

| Severity | Rule | Violations | Regulation |
|---|---|---|---|
| CRITICAL | `transactions_ctr_filing_required` | 8 | BSA 31 U.S.C. § 5313 |
| CRITICAL | `transactions_structuring_detection` | 4 | 31 U.S.C. § 5324 |
| CRITICAL | `transactions_ofac_sanctions_screening` | 2 | OFAC SDN — 31 C.F.R. Parts 500-598 |
| CRITICAL | `counterparties_name_ofac_sanctions_check` | 2 | OFAC SDN |
| CRITICAL | `transactions_pep_sar_required` | 1 | FinCEN FIN-2012-G003 |
| HIGH | `transactions_velocity_breach` | 2 | Internal policy P-06 |
| HIGH | `transactions_dormant_reactivation_large_wire` | 1 | Internal policy P-07 |
| HIGH | `transactions_new_account_large_wire` | 1 | Internal policy P-08 |
| MEDIUM | `transactions_round_amount_concentration` | 18 | Internal anomaly P-09 |
| MEDIUM | `transactions_counterparty_concentration` | 13 | Internal anomaly P-10 |
| MEDIUM | `transactions_geographic_mismatch` | 2 | Internal anomaly P-11 |

**4. Run the same pipeline via Hermes**

```
Load the pipeline at demo/fraud/pipeline.yaml and run it.
```

One prompt. Hermes handles the rest.

---

## Scheduling with Hermes

Hermes can schedule Aegis validations on a recurring cadence:

```
Run the fraud-aml pipeline every morning at 8am and alert me in Slack
if anything is CRITICAL severity.
```

Hermes owns the schedule and alerting. Aegis owns the validation and diagnosis. Every run is logged to the audit trail automatically.

---

## Troubleshooting

**Hermes can't find the `aegis` command**
: Ensure `aegis-dq` is installed in the same Python environment Hermes uses. Run `which aegis` to confirm, then set the full path in `command:` if needed.

**`"Could not resolve authentication method"` error**
: The `ANTHROPIC_API_KEY` (or equivalent) is not set. Add it to `~/.hermes/.env` or the `env:` block in your Hermes MCP server config.

**`"Missing required connection params"` error**
: The warehouse env vars are not set in your Hermes `mcp_servers.aegis.env` block. Check the warehouse setup tab in the [Setup](#setup) section.

**LLM diagnosis is slow or expensive**
: Switch to `claude-haiku-4-5-20251001` in your Hermes config — 10× cheaper than Sonnet with comparable quality for DQ diagnosis tasks.

**Generated rules have SQL syntax errors**
: The most common issue is date functions. DuckDB uses `date_diff('day', start, end)` not `DATEDIFF(day, ...)`. Test individual queries directly against DuckDB before running the full pipeline.

**Validation passes but failures were expected**
: Check that the `table` field in your rules matches the exact table name in the warehouse (case-sensitive on some engines). Run `aegis generate --no-llm` first to confirm schema introspection works.

---

## See also

- [MCP Clients](mcp-clients.md) — Claude Desktop, Cursor, Cline setup
- [MCP Server reference](mcp.md) — full tool documentation and parameters
- [Rule Schema Reference](../rule-schema-reference.md) — writing and generating rules
- [CLI Reference](../cli-reference.md) — `aegis generate`, `aegis pipeline`, `aegis run`
