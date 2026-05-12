# Aegis

**Open, audit-grade agentic data quality framework with portable industry packs.**

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)
[![CI](https://github.com/Shivakoreddi/aegis-dq/actions/workflows/ci.yml/badge.svg)](https://github.com/Shivakoreddi/aegis-dq/actions)
[![Tests](https://img.shields.io/badge/tests-101%20passing-brightgreen)](#)

Aegis runs a **LangGraph-orchestrated agent** that validates your data, diagnoses failures with an LLM, and logs every decision to an audit trail — with every cost metered and every finding exportable.

---

## Why Aegis?

| | Aegis | Great Expectations / Soda | Monte Carlo / Anomalo |
|---|---|---|---|
| Open source | ✅ Apache 2.0 | ✅ | ❌ Commercial |
| Agentic (LLM diagnosis + RCA) | ✅ | ❌ Rule execution only | ✅ Proprietary |
| Audit trail (per-decision log) | ✅ | Partial | ✅ Proprietary |
| Pluggable LLM (Anthropic, OpenAI) | ✅ | ❌ | ❌ |
| Industry packs | ✅ Planned | ❌ | ❌ |
| Portable open rule standard (ODCS-aligned) | ✅ | Partial | ❌ |

---

## Install

```bash
pip install aegis-dq
```

For development:

```bash
git clone https://github.com/Shivakoreddi/aegis-dq
cd aegis-dq
pip install -e ".[dev]"
```

Optional extras:

```bash
pip install aegis-dq[openai]     # OpenAI LLM provider
pip install aegis-dq[snowflake]  # Snowflake warehouse adapter (coming in v0.5)
```

---

## 5-minute quickstart

```bash
# 1. Generate an example rules file
aegis init

# 2. Validate syntax before touching any warehouse (offline, no API key)
aegis validate rules.yaml

# 3. Run checks offline
aegis run rules.yaml --no-llm

# 4. Run with LLM diagnosis (Anthropic by default)
export ANTHROPIC_API_KEY=sk-ant-...
aegis run rules.yaml

# 5. Use OpenAI instead
export OPENAI_API_KEY=sk-...
aegis run rules.yaml --llm openai

# 6. Write a JSON report and notify Slack on failure
aegis run rules.yaml \
  --output-json report.json \
  --notify https://hooks.slack.com/services/...
```

**Full walkthrough with real data:** [docs/getting-started.md](docs/getting-started.md)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  TIER 1 — INTERFACES                                         │
│  CLI (aegis run/validate/init)  •  Python SDK  •  REST API   │
│  Triggers: Airflow • dbt • Dagster • cron • webhook          │
│  Outputs:  Slack • Email • PagerDuty • Jira • file           │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  TIER 2 — AGENT CORE  (LangGraph state machine)              │
│                                                              │
│  plan → execute → diagnose → report                          │
│            ↓          ↓         ↓                            │
│       Rule Engine  LLM Router  Audit Logger                  │
│       25 types     Anthropic   SQLite + ShareGPT export      │
│                    OpenAI                                     │
│                                                              │
│  Memory: run history • failure patterns • rule catalog       │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  TIER 3 — EXECUTION BACKENDS                                 │
│  DuckDB (local/free)  •  Snowflake  •  BigQuery              │
│  Databricks  •  Athena  •  Postgres  •  Redshift             │
└──────────────────────────────────────────────────────────────┘
```

---

## Rule format

```yaml
rules:
  - apiVersion: aegis.dev/v1
    kind: DataQualityRule
    metadata:
      id: orders_revenue_non_negative
      severity: critical          # critical | high | medium | low | info
      domain: retail
      owner: revenue-team
      tags: [revenue, validity]
      description: Revenue must be >= 0
    scope:
      warehouse: duckdb
      table: orders
    logic:
      type: sql_expression
      expression: "revenue >= 0"
    diagnosis:
      common_causes:
        - "Refund logic inverted the sign"
        - "Currency conversion failure"
```

All 25 rule types with examples: [docs/rule-schema-reference.md](docs/rule-schema-reference.md)

Browse the 30 built-in templates:

```bash
aegis rules list
aegis rules list --category validity
```

---

## CLI reference

| Command | Description |
|---|---|
| `aegis init` | Generate a starter `rules.yaml` |
| `aegis validate <config>` | Check YAML syntax + schema offline (no warehouse needed) |
| `aegis run <config>` | Run validation, diagnose failures, produce a report |
| `aegis rules list` | Browse the 30 built-in rule templates |
| `aegis audit trajectory <run-id>` | Inspect the LLM decision trail for a past run |

**`aegis run` flags:**

| Flag | Default | Description |
|---|---|---|
| `--db` | `:memory:` | DuckDB file path |
| `--llm` | `anthropic` | LLM provider: `anthropic` \| `openai` |
| `--llm-model` | *(provider default)* | Override model name |
| `--no-llm` | `false` | Skip LLM diagnosis entirely |
| `--output-json` | *(none)* | Write full JSON report to file |
| `--notify` | *(none)* | Slack webhook URL |
| `--notify-on` | `failures` | When to notify: `all` \| `failures` \| `critical` |

---

## Rule types (25 total)

| Category | Types |
|---|---|
| Completeness | `not_null` `not_empty_string` `null_percentage_below` |
| Uniqueness | `unique` `composite_unique` `duplicate_percentage_below` |
| Validity | `sql_expression` `between` `min_value_check` `max_value_check` `regex_match` `accepted_values` `not_accepted_values` `no_future_dates` `column_exists` |
| Referential | `foreign_key` `conditional_not_null` |
| Statistical | `mean_between` `stddev_below` `column_sum_between` |
| Timeliness | `freshness` `date_order` |
| Volume | `row_count` `row_count_between` `custom_sql` |

---

## Roadmap

| Phase | Version | Status |
|---|---|---|
| Foundation | v0.1 | 🚧 In progress |
| Differentiate | v0.5 | Planned — RCA, reconciliation, BigQuery, Airflow, industry packs |
| Mature | v1.0 | Planned — ML rules, banking/healthcare packs, VS Code extension |

Full issue tracker: [github.com/Shivakoreddi/aegis-dq/issues](https://github.com/Shivakoreddi/aegis-dq/issues)

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.
Good first issues: [label:good first issue](https://github.com/Shivakoreddi/aegis-dq/issues?q=label%3A%22good+first+issue%22)

## License

[Apache 2.0](LICENSE)
