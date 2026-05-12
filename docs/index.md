# Aegis

**Open, audit-grade agentic data quality framework with portable industry packs.**

Aegis runs a **LangGraph-orchestrated agent** that validates your data, diagnoses failures with an LLM, and logs every decision to an audit trail — with every cost metered and every finding exportable.

---

## Install

```bash
pip install aegis-dq
```

## Quickstart

```bash
# Generate a starter rules file
aegis init

# Validate syntax offline
aegis validate rules.yaml

# Run checks without LLM
aegis run rules.yaml --no-llm

# Run with LLM diagnosis (Anthropic by default)
export ANTHROPIC_API_KEY=sk-ant-...
aegis run rules.yaml
```

**Full walkthrough:** [Getting Started](getting-started.md)

---

## Why Aegis?

| | Aegis | Great Expectations / Soda | Monte Carlo / Anomalo |
|---|---|---|---|
| Open source | ✅ Apache 2.0 | ✅ | ❌ Commercial |
| Agentic (LLM diagnosis + RCA) | ✅ | ❌ Rule execution only | ✅ Proprietary |
| Audit trail (per-decision log) | ✅ | Partial | ✅ Proprietary |
| Pluggable LLM (Anthropic, OpenAI) | ✅ | ❌ | ❌ |
| Industry packs | ✅ Planned | ❌ | ❌ |
| Portable open rule standard | ✅ | Partial | ❌ |

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
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  TIER 3 — EXECUTION BACKENDS                                 │
│  DuckDB (local/free)  •  Snowflake  •  BigQuery              │
│  Databricks  •  Athena  •  Postgres  •  Redshift             │
└──────────────────────────────────────────────────────────────┘
```

---

## Rule types (25 total)

| Category | Types |
|---|---|
| Completeness | `not_null` `not_empty_string` `null_percentage_below` |
| Uniqueness | `unique` `composite_unique` `duplicate_percentage_below` |
| Validity | `sql_expression` `between` `min_value_check` `max_value_check` `regex_match` `accepted_values` `not_accepted_values` `no_future_dates` `column_exists` `date_order` |
| Referential | `foreign_key` `conditional_not_null` |
| Statistical | `mean_between` `stddev_below` `column_sum_between` |
| Timeliness | `freshness` |
| Volume | `row_count` `row_count_between` `custom_sql` |

---

## Links

- [GitHub](https://github.com/Shivakoreddi/aegis-dq)
- [PyPI](https://pypi.org/project/aegis-dq/)
- [Issue tracker](https://github.com/Shivakoreddi/aegis-dq/issues)
