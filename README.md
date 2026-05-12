# Aegis DQ

[![CI](https://github.com/aegis-dq/aegis-dq/actions/workflows/ci.yml/badge.svg)](https://github.com/aegis-dq/aegis-dq/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/aegis-dq)](https://pypi.org/project/aegis-dq/)
[![Downloads](https://img.shields.io/pypi/dm/aegis-dq)](https://pypi.org/project/aegis-dq/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)
[![GitHub Marketplace](https://img.shields.io/badge/GitHub%20Marketplace-Aegis%20DQ-blueviolet?logo=github)](https://github.com/marketplace/actions/aegis-dq)
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/aegis-dq/aegis-dq/blob/main/notebooks/quickstart.ipynb)

**The open-source agentic data quality framework.** Validate data contracts, diagnose failures with LLM root-cause analysis, and auto-generate SQL remediation — all in a single CI step or Python call.

- **31 rule types** — completeness, uniqueness, validity, referential integrity, statistical, ML anomaly detection
- **6 warehouse adapters** — DuckDB, Postgres/Redshift, BigQuery, Databricks, AWS Athena, Snowflake
- **Pluggable LLMs** — Anthropic Claude, OpenAI, Ollama (local), AWS Bedrock
- **Agentic pipeline** — plan → parallel validation → LLM diagnose → RCA → SQL remediate → report

---

## GitHub Actions — Quick Start

Add a data quality gate to any workflow in under 2 minutes:

```yaml
# .github/workflows/data-quality.yml
name: Data Quality

on: [push, pull_request]

jobs:
  data-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Validate data quality
        uses: aegis-dq/aegis-dq@v0.5.0
        with:
          rules-file: rules.yaml
          db: data/warehouse.duckdb
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

The step **fails the job automatically** when any rules fail, blocking broken data from reaching production. Set `fail-on-failure: 'false'` to report without blocking.

**Offline mode (no API key required):**

```yaml
      - name: Validate data quality (offline)
        uses: aegis-dq/aegis-dq@v0.5.0
        with:
          rules-file: rules.yaml
          db: data/warehouse.duckdb
          no-llm: 'true'
```

### Action inputs

| Input | Default | Description |
|---|---|---|
| `rules-file` | `rules.yaml` | Path to rules YAML |
| `db` | `:memory:` | DuckDB file path |
| `warehouse` | `duckdb` | `duckdb` · `postgres` · `redshift` |
| `pg-dsn` | — | PostgreSQL / Redshift connection DSN |
| `no-llm` | `false` | Skip LLM — free offline validation |
| `llm` | `anthropic` | `anthropic` · `openai` · `ollama` |
| `llm-model` | *(provider default)* | Override the default model |
| `fail-on-failure` | `true` | Fail the step when rules fail |
| `version` | *(latest)* | Pin a specific `aegis-dq` version |
| `anthropic-api-key` | — | Required when `llm: anthropic` |
| `openai-api-key` | — | Required when `llm: openai` |

### Action outputs

| Output | Description |
|---|---|
| `rules-checked` | Total rules evaluated |
| `passed` | Rules that passed |
| `failed` | Rules that failed |
| `pass-rate` | Pass rate as a decimal (e.g. `"91.67"`) |
| `report-json` | Absolute path to the full JSON report |

**Using outputs in downstream steps:**

```yaml
      - name: Validate data quality
        id: dq
        uses: aegis-dq/aegis-dq@v0.5.0
        with:
          rules-file: rules.yaml

      - name: Post summary
        run: echo "Pass rate: ${{ steps.dq.outputs.pass-rate }}%"
```

---

## Demo

![Aegis DQ Demo](docs/demo.gif)

```
╭──────────────────────────────────────────────────────╮
│ Aegis DQ  —  RetailCo E-commerce Demo                │
│ LLM: amazon.nova-pro-v1:0 via AWS Bedrock            │
╰──────────────────────────────────────────────────────╯

✓ Pipeline complete in 7.1s · 12 rules · $0.0056 LLM cost

╭──────────────── Validation Summary ─────────────────╮
│  Rules checked  │  12                               │
│  Passed         │  1   │  Failed  │  11             │
│  Pass rate      │  8%  │  Cost    │  $0.005576      │
╰─────────────────────────────────────────────────────╯

LLM Diagnoses
  orders_customer_fk  →  Order placed with customer_id=99 that does not exist.
                         Likely cause: customer deleted or test record not cleaned up.

  products_sku_unique →  Duplicate SKU-001 — two products share the same identifier.
                         Likely cause: duplicate import from supplier feed.

Remediation SQL (LLM-generated)
  orders_status_valid          UPDATE orders SET status = 'SHIPPED' WHERE status = 'DISPATCHED';
  products_price_positive      UPDATE products SET price = ABS(price) WHERE price < 0;
  products_stock_non_negative  UPDATE products SET stock_quantity = 0 WHERE stock_quantity < 0;
```

---

## Why Aegis?

| | Aegis DQ | Great Expectations / Soda | Monte Carlo / Anomalo |
|---|---|---|---|
| Open source | ✅ Apache 2.0 | ✅ | ❌ Commercial |
| Agentic LLM diagnosis + RCA | ✅ | ❌ | ✅ Proprietary |
| SQL auto-fix proposals | ✅ | ❌ | ❌ |
| Audit trail (per-decision log) | ✅ | Partial | ✅ Proprietary |
| Pluggable LLM (Anthropic, OpenAI, Bedrock, Ollama) | ✅ | ❌ | ❌ |
| dbt integration | ✅ | ✅ | Partial |
| Portable open rule standard | ✅ | Partial | ❌ |
| ML anomaly detection | ✅ built-in | ❌ | ✅ Proprietary |

---

## Install

```bash
pip install aegis-dq
```

| Extra | What it adds |
|---|---|
| `aegis-dq[bigquery]` | BigQuery adapter |
| `aegis-dq[databricks]` | Databricks adapter |
| `aegis-dq[athena]` | AWS Athena adapter |
| `aegis-dq[postgres]` | PostgreSQL / Redshift adapter |
| `aegis-dq[snowflake]` | Snowflake adapter |
| `aegis-dq[rest]` | REST API server (FastAPI + uvicorn) |
| `aegis-dq[openai]` | OpenAI LLM provider |
| `aegis-dq[airflow]` | Airflow `AegisOperator` |
| `aegis-dq[mcp]` | MCP server for Claude Desktop |
| `aegis-dq[ml]` | scikit-learn anomaly detection |

---

## 5-minute quickstart

Seed a demo DuckDB database:

```python
import duckdb

con = duckdb.connect("demo.db")
con.execute("""
    CREATE TABLE orders AS
    SELECT i AS order_id, 'placed' AS status, i * 9.99 AS revenue
    FROM range(1, 10001) t(i)
""")
# introduce some bad data
con.execute("UPDATE orders SET order_id = NULL WHERE order_id % 200 = 0")
con.execute("UPDATE orders SET revenue = -5.00 WHERE order_id % 500 = 0")
con.close()
```

Generate a starter rules file and run:

```bash
aegis init

export ANTHROPIC_API_KEY=sk-ant-...
aegis run rules.yaml --db demo.db
```

Run without an API key (validation only, no LLM diagnosis):

```bash
aegis run rules.yaml --db demo.db --no-llm
```

---

## Pipeline

Every `aegis run` passes your data through a LangGraph pipeline:

```
rules (Python / YAML)
    │
    ▼
  plan ──► parallel_table ──► reconcile ──► remediate ──► report
                 │
         ┌──────────────────┐
         │  per table:      │
         │  execute         │
         │  classify        │
         │  diagnose        │  ← concurrent across all tables
         │  rca             │
         └──────────────────┘
```

- **plan** — parse and validate rules, build an execution graph
- **parallel_table** — concurrently fans out per table: execute all rules, classify failures by severity, diagnose with LLM, and trace root causes
- **reconcile** — compare results against expected thresholds
- **remediate** — LLM proposes a targeted SQL fix for each diagnosed failure
- **report** — structured JSON + optional Slack notification

---

## Rule types (31 total)

| Category | Types |
|---|---|
| Completeness | `not_null` `not_empty_string` `null_percentage_below` |
| Uniqueness | `unique` `composite_unique` `duplicate_percentage_below` |
| Validity | `sql_expression` `between` `min_value_check` `max_value_check` `regex_match` `accepted_values` `not_accepted_values` `no_future_dates` `column_exists` |
| Referential | `foreign_key` `conditional_not_null` |
| Statistical | `mean_between` `stddev_below` `column_sum_between` |
| Timeliness | `freshness` `date_order` |
| Volume | `row_count` `row_count_between` `custom_sql` |
| Cross-table | `reconcile_row_count` `reconcile_column_sum` `reconcile_key_match` |
| ML / Anomaly | `zscore_outlier` `isolation_forest` `learned_threshold` |

Example rule:

```yaml
rules:
  - apiVersion: aegis.dev/v1
    kind: DataQualityRule
    metadata:
      id: orders_revenue_non_negative
      severity: critical
      owner: revenue-team
      tags: [revenue, validity]
    scope:
      warehouse: duckdb
      table: orders
    logic:
      type: sql_expression
      expression: "revenue >= 0"
```

---

## Warehouse adapters

| Adapter | Install | Status |
|---|---|---|
| DuckDB | built-in | ✅ GA |
| BigQuery | `aegis-dq[bigquery]` | ✅ GA |
| Databricks | `aegis-dq[databricks]` | ✅ GA |
| AWS Athena | `aegis-dq[athena]` | ✅ GA |
| Postgres / Redshift | `aegis-dq[postgres]` | ✅ GA |
| Snowflake | `aegis-dq[snowflake]` | ✅ GA |

---

## LLM providers

| Provider | Install | Default model |
|---|---|---|
| Anthropic (Claude) | built-in | `claude-haiku-4-5` |
| OpenAI | `aegis-dq[openai]` | `gpt-4o-mini` |
| Ollama (local) | `aegis-dq[ollama]` | `llama3.2` |
| AWS Bedrock | `pip install boto3` | `amazon.nova-pro-v1:0` |

Switch providers at the CLI:

```bash
aegis run rules.yaml --llm openai --llm-model gpt-4o
aegis run rules.yaml --llm ollama --llm-model llama3.2
aegis run rules.yaml --llm bedrock --llm-model amazon.nova-pro-v1:0
```

---

## Integrations

| Integration | What it does |
|---|---|
| GitHub Action | CI/CD gate — fails the job when rules fail |
| `aegis-dq[rest]` | REST API server — `aegis serve` |
| `aegis-dq[airflow]` | `AegisOperator` — drop-in Airflow task |
| `aegis-dq[mcp]` | MCP server for Claude Desktop / tool use |
| `aegis dbt generate` | Convert dbt `manifest.json` to Aegis rules |

---

## CLI reference

| Command | Description |
|---|---|
| `aegis init` | Generate a starter `rules.yaml` |
| `aegis validate <config>` | Check YAML syntax + schema (no warehouse needed) |
| `aegis generate <table>` | LLM-generate rules from table schema |
| `aegis run <config>` | Run validation, diagnose failures, produce a report |
| `aegis rules list` | Browse built-in rule templates |
| `aegis audit trajectory <run-id>` | Inspect the LLM decision trail for a past run |
| `aegis audit search <query>` | Full-text search across audit logs |
| `aegis dbt generate <manifest>` | Convert a dbt manifest to Aegis rules |
| `aegis mcp serve` | Start the MCP server for Claude Desktop |

**`aegis run` flags:**

| Flag | Default | Description |
|---|---|---|
| `--db` | `:memory:` | DuckDB file path |
| `--llm` | `anthropic` | LLM provider |
| `--llm-model` | *(provider default)* | Override model name |
| `--no-llm` | `false` | Skip LLM diagnosis entirely |
| `--output-json` | *(none)* | Write full JSON report to file |
| `--notify` | *(none)* | Slack webhook URL |
| `--notify-on` | `failures` | When to notify: `all` · `failures` · `critical` |

---

## Roadmap

| Phase | Version | Items | Status |
|---|---|---|---|
| Foundation | v0.1 | Core agent, DuckDB, CLI, audit trail | ✅ Done |
| Differentiate | v0.5 | BigQuery, Databricks, Athena, Airflow, Ollama, RCA, ShareGPT export, FTS5 search, dbt, MCP | ✅ Done |
| Mature | v1.0 | Postgres, REST API, GitHub Action, parallel subagents, VS Code extension, eval suite, ML anomaly detection, banking/healthcare packs | 🚧 In progress |

Full issue tracker: [github.com/aegis-dq/aegis-dq/issues](https://github.com/aegis-dq/aegis-dq/issues)

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

Good first issues: [label:good first issue](https://github.com/aegis-dq/aegis-dq/issues?q=label%3A%22good+first+issue%22)

## License

[Apache 2.0](LICENSE)
