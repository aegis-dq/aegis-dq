# Aegis DQ

[![PyPI](https://img.shields.io/pypi/v/aegis-dq)](https://pypi.org/project/aegis-dq/)
[![Downloads](https://img.shields.io/pypi/dm/aegis-dq)](https://pypi.org/project/aegis-dq/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-323%20passing-brightgreen)](.github/workflows/ci.yml)
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/aegis-dq/aegis-dq/blob/main/notebooks/quickstart.ipynb)

![Aegis DQ Demo](docs/demo.gif)

**Open-source agentic data quality: validate, diagnose, and explain data failures — with an LLM that tells you exactly why.**

---

```
$ aegis run demo/rules.yaml --db demo.db

Aegis DQ — loading rules from demo/rules.yaml
Loaded 3 rules
LLM: Anthropic (claude-haiku-4-5-20251001)

 Aegis Validation Report
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Metric        ┃ Value      ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ Rules checked │ 3          │
│ Passed        │ 1          │
│ Failed        │ 2          │
│ Pass rate     │ 33.3%      │
│ LLM cost      │ $0.000241  │
└───────────────┴────────────┘

Failures:

  orders_no_null_order_id (critical) — orders
  Rows failed: 50 / 10,000
  Explanation:  50 rows have NULL order_id, violating the completeness rule.
  Likely cause: ETL pipeline failed to populate order_id for a batch of
                orders, leaving primary keys unset.
  Action:       Identify the ingestion job that produced NULL order_ids and
                re-run it with a backfill for the affected window.

  orders_positive_revenue (high) — orders
  Rows failed: 20 / 10,000
  Explanation:  20 rows have negative revenue values, which violates the
                business rule that all transactions must be non-negative.
  Likely cause: A refund or adjustment record was written with a negative
                amount instead of a separate credit entry.
  Action:       Audit the revenue column for refund records and apply the
                correct accounting treatment.
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
| `aegis-dq[openai]` | OpenAI LLM provider |
| `aegis-dq[ollama]` | Ollama (local) LLM provider |
| `aegis-dq[airflow]` | Airflow `AegisOperator` |
| `aegis-dq[mcp]` | MCP server for Claude Desktop |

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

Every `aegis run` passes your data through a 7-node LangGraph pipeline:

```
rules.yaml
    │
    ▼
  plan → execute → reconcile → classify → diagnose → rca → report
           │                       │           │        │       │
        28 rule               heuristic    LLM asks  lineage  JSON +
        types                  + LLM       "why?"    context  Slack
```

- **plan** — parse and validate rules.yaml, build an execution graph
- **execute** — run all 28 rule types against your warehouse
- **reconcile** — compare results against expected thresholds
- **classify** — heuristic triage (severity, category, affected rows)
- **diagnose** — LLM writes a plain-English explanation per failure
- **rca** — root-cause analysis using lineage context and run history
- **report** — structured JSON + optional Slack notification

---

## Rule types (28 total)

| Category | Types |
|---|---|
| Completeness | `not_null` `not_empty_string` `null_percentage_below` |
| Uniqueness | `unique` `composite_unique` `duplicate_percentage_below` |
| Validity | `sql_expression` `between` `min_value_check` `max_value_check` `regex_match` `accepted_values` `not_accepted_values` `no_future_dates` `column_exists` |
| Referential | `foreign_key` `conditional_not_null` |
| Statistical | `mean_between` `stddev_below` `column_sum_between` |
| Timeliness | `freshness` `date_order` |
| Volume | `row_count` `row_count_between` `custom_sql` |
| Cross-table | `row_count_match` `column_sum_match` `set_inclusion` `set_equality` |

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

Switch providers at the CLI:

```bash
aegis run rules.yaml --llm openai --llm-model gpt-4o
aegis run rules.yaml --llm ollama --llm-model llama3.2
```

---

## Integrations

| Integration | What it does |
|---|---|
| `aegis-dq[airflow]` | `AegisOperator` — drop-in Airflow task |
| `aegis-dq[mcp]` | MCP server for Claude Desktop / tool use |
| `aegis dbt generate` | Convert dbt `manifest.json` to Aegis rules |
| GitHub Action (#27) | CI/CD gate on PRs *(coming v1.0)* |

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
| Mature | v1.0 | ~~Postgres~~, REST API, GitHub Action, parallel subagents, ML anomaly detection, banking/healthcare packs | 🚧 In progress |

Full issue tracker: [github.com/aegis-dq/aegis-dq/issues](https://github.com/aegis-dq/aegis-dq/issues)

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

Good first issues: [label:good first issue](https://github.com/aegis-dq/aegis-dq/issues?q=label%3A%22good+first+issue%22)

## License

[Apache 2.0](LICENSE)
