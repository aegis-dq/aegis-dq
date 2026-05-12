# Aegis DQ

[![PyPI](https://img.shields.io/pypi/v/aegis-dq)](https://pypi.org/project/aegis-dq/)
[![Downloads](https://img.shields.io/pypi/dm/aegis-dq)](https://pypi.org/project/aegis-dq/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-535%20passing-brightgreen)](.github/workflows/ci.yml)
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/aegis-dq/aegis-dq/blob/main/notebooks/quickstart.ipynb)

![Aegis DQ Demo](docs/demo.gif)

**Open-source agentic data quality: validate, diagnose, and explain data failures — with an LLM that tells you exactly why.**

---

```
$ python demo/realworld_demo.py --aws-profile mcal-research

╭──────────────────────────────────────────────────────╮
│ Aegis DQ  —  RetailCo E-commerce Demo                │
│ LLM: amazon.nova-pro-v1:0 via AWS Bedrock            │
╰──────────────────────────────────────────────────────╯

✓ Database ready: 4 tables, realistic dirty data injected
  Rules loaded: 12 rules across 4 tables

  Running Aegis pipeline...
    plan → parallel_table → reconcile → remediate → report

✓ Pipeline complete in 7.1s

╭──────────────── Validation Summary ─────────────────╮
│  Rules checked  │  12                               │
│  Passed         │  1                                │
│  Failed         │  11                               │
│  Pass rate      │  8%                               │
│  LLM cost       │  $0.005576                        │
│  Total tokens   │  3,614                            │
╰─────────────────────────────────────────────────────╯

Failures by Severity
  ● CRITICAL (6)  customers_email_not_null · orders_amount_positive
                  orders_customer_fk · payments_order_fk
                  products_price_positive · products_sku_unique
  ● HIGH     (4)  customers_email_not_empty · orders_date_order
                  orders_status_valid · products_stock_non_negative
  ● MEDIUM   (1)  customers_tier_accepted

LLM Diagnoses ─────────────────────────────────────────────
  orders_customer_fk → orders
  Explanation:  Order placed with customer_id=99 that does not exist in customers.
  Likely cause: Customer was deleted or is a test account not cleaned up.
  Action:       Verify customer_id=99; check for recent deletions or orphan test data.

  products_sku_unique → products
  Explanation:  Duplicate SKU-001 found — two products share the same identifier.
  Likely cause: Duplicate import from supplier feed or product versioning reused old SKU.
  Action:       Investigate recent import logs and product versioning history.

Root-Cause Analysis ────────────────────────────────────────
  products_price_positive  Root cause: data entry error or promo discount bug
                           Fix: implement validation on price > 0 before insert

Remediation Proposals (LLM-generated SQL) ─────────────────
  orders_status_valid        UPDATE orders SET status = 'SHIPPED' WHERE status = 'DISPATCHED';
  products_price_positive    UPDATE products SET price = ABS(price) WHERE product_id = 5 AND price < 0;
  products_stock_non_negative UPDATE products SET stock_quantity = 0 WHERE stock_quantity < 0 AND product_sku = 'SKU-010';
```

---

## Why Aegis?

| | Aegis DQ | Great Expectations / Soda | Monte Carlo / Anomalo |
|---|---|---|---|
| Open source | ✅ Apache 2.0 | ✅ | ❌ Commercial |
| Agentic LLM diagnosis + RCA | ✅ | ❌ | ✅ Proprietary |
| Audit trail (per-decision log) | ✅ | Partial | ✅ Proprietary |
| Pluggable LLM (Anthropic, OpenAI, Ollama) | ✅ | ❌ | ❌ |
| dbt integration | ✅ | ✅ | Partial |
| Portable open rule standard | ✅ | Partial | ❌ |

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
| `aegis-dq[rest]` | REST API server (FastAPI + uvicorn) |
| `aegis-dq[openai]` | OpenAI LLM provider |
| `aegis-dq[ollama]` | Ollama (local) LLM provider |
| `aegis-dq[airflow]` | Airflow `AegisOperator` |
| `aegis-dq[mcp]` | MCP server for Claude Desktop |
| `aegis-dq[ml]` | scikit-learn anomaly detection (`zscore_outlier`, `isolation_forest`, `learned_threshold`) |

---

## 5-minute quickstart

```bash
pip install aegis-dq
```

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
# create rules.yaml
aegis init

# edit rules.yaml — set warehouse: duckdb and table: orders
# then run validation
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
- **parallel_table** — Concurrently fans out per table: execute all rules, classify failures by severity, diagnose with LLM, and trace root causes — all tables run in parallel via `asyncio.gather`
- **reconcile** — compare results against expected thresholds
- **remediate** — LLM proposes a targeted SQL fix for each diagnosed failure based on the rule type, diagnosis, and RCA context
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
| DuckDB | built-in | ✅ |
| BigQuery | `aegis-dq[bigquery]` | ✅ |
| Databricks | `aegis-dq[databricks]` | ✅ |
| AWS Athena | `aegis-dq[athena]` | ✅ |
| Snowflake | `aegis-dq[snowflake]` | ✅ coming v1.0 |
| Postgres / Redshift | `aegis-dq[postgres]` | ✅ |

---

## LLM providers

| Provider | Install | Default model |
|---|---|---|
| Anthropic (Claude) | built-in | claude-haiku-4-5 |
| OpenAI | `aegis-dq[openai]` | gpt-4o-mini |
| Ollama (local) | `aegis-dq[ollama]` | llama3.2 |
| AWS Bedrock | `pip install boto3` | amazon.nova-pro-v1:0 |

Switch providers at the CLI:

```bash
aegis run rules.yaml --llm openai --llm-model gpt-4o
aegis run rules.yaml --llm ollama --llm-model llama3.2
```

```bash
# AWS Bedrock (Nova Pro, no approval form required)
python demo/realworld_demo.py --aws-profile your-profile
```

---

## Integrations

| Integration | What it does |
|---|---|
| `aegis-dq[rest]` | REST API server — `aegis serve` |
| `aegis-dq[airflow]` | `AegisOperator` — drop-in Airflow task |
| `aegis-dq[mcp]` | MCP server for Claude Desktop / tool use |
| `aegis dbt generate` | Convert dbt `manifest.json` to Aegis rules |
| GitHub Action | CI/CD gate on PRs — fails the job when rules fail |

### GitHub Action

```yaml
# .github/workflows/data-quality.yml
name: Data Quality

on: [push, pull_request]

jobs:
  aegis:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Aegis DQ
        uses: aegis-dq/aegis-dq@v0.5.0
        with:
          rules-file: rules.yaml
          db: data/warehouse.db
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}

      # Without LLM (free, validation only)
      # - name: Run Aegis DQ (offline)
      #   uses: aegis-dq/aegis-dq@v0.5.0
      #   with:
      #     rules-file: rules.yaml
      #     no-llm: 'true'
```

The job fails automatically if any rules fail. Set `fail-on-failure: 'false'` to report without blocking the pipeline.

**Action inputs:**

| Input | Default | Description |
|---|---|---|
| `rules-file` | `rules.yaml` | Path to rules YAML |
| `db` | `:memory:` | DuckDB file path |
| `warehouse` | `duckdb` | `duckdb` \| `postgres` \| `redshift` |
| `pg-dsn` | — | PostgreSQL / Redshift DSN |
| `no-llm` | `false` | Skip LLM diagnosis |
| `llm` | `anthropic` | `anthropic` \| `openai` \| `ollama` |
| `llm-model` | *(provider default)* | Override model |
| `fail-on-failure` | `true` | Fail step on rule failures |
| `version` | *(latest)* | Pin aegis-dq version |
| `anthropic-api-key` | — | Anthropic API key secret |
| `openai-api-key` | — | OpenAI API key secret |

**Action outputs:** `rules-checked`, `passed`, `failed`, `pass-rate`, `report-json`

---

## CLI reference

| Command | Description |
|---|---|
| `aegis init` | Generate a starter `rules.yaml` |
| `aegis validate <config>` | Check YAML syntax + schema (no warehouse needed) |
| `aegis run <config>` | Run validation, diagnose failures, produce a report |
| `aegis rules list` | Browse built-in rule templates |
| `aegis audit trajectory <run-id>` | Inspect the LLM decision trail for a past run |
| `aegis audit search <query>` | Full-text search across audit logs (FTS5) |
| `aegis dbt generate <manifest>` | Convert a dbt manifest to Aegis rules |
| `aegis mcp serve` | Start the MCP server for Claude Desktop |

**`aegis run` flags:**

| Flag | Default | Description |
|---|---|---|
| `--db` | `:memory:` | DuckDB file path |
| `--llm` | `anthropic` | LLM provider: `anthropic` \| `openai` \| `ollama` |
| `--llm-model` | *(provider default)* | Override model name |
| `--no-llm` | `false` | Skip LLM diagnosis entirely |
| `--output-json` | *(none)* | Write full JSON report to file |
| `--notify` | *(none)* | Slack webhook URL |
| `--notify-on` | `failures` | When to notify: `all` \| `failures` \| `critical` |

---

## Roadmap

| Phase | Version | Items | Status |
|---|---|---|---|
| Foundation | v0.1 | Core agent, DuckDB, CLI, audit trail | ✅ Done |
| Differentiate | v0.5 | BigQuery, Databricks, Athena, Airflow, Ollama, RCA, ShareGPT export, FTS5 search, dbt, MCP | ✅ Done |
| Mature | v1.0 | ~~Postgres~~, ~~REST API~~, ~~GitHub Action~~, ~~parallel subagents~~, ~~VS Code extension~~, ~~eval suite~~, ~~ML anomaly detection~~, banking/healthcare packs | 🚧 In progress |

Full issue tracker: [github.com/aegis-dq/aegis-dq/issues](https://github.com/aegis-dq/aegis-dq/issues)

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

Good first issues: [label:good first issue](https://github.com/aegis-dq/aegis-dq/issues?q=label%3A%22good+first+issue%22)

## License

[Apache 2.0](LICENSE)
