# Aegis

**Open, audit-grade agentic data quality framework — LLM-powered diagnosis, full audit trail, runs everywhere.**

Aegis orchestrates a **7-node LangGraph pipeline** that validates your data, diagnoses failures with an LLM, traces root causes through your lineage graph, and logs every decision to a searchable audit trail — all from a single YAML file.

[Get Started in 5 minutes](getting-started.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/aegis-dq/aegis-dq){ .md-button }

---

## See it in action

```
$ aegis run rules.yaml --db demo.db

Aegis DQ — loading rules from rules.yaml
Loaded 3 rules  •  warehouse: duckdb  •  llm: anthropic/claude-haiku-4-5

Running pipeline: plan → execute → reconcile → classify → diagnose → rca → report

  ✓  orders_minimum_rows          passed    10 000 rows   —
  ✗  orders_order_id_not_null     FAILED    50 / 10 000   critical
  ✗  orders_revenue_positive      FAILED    20 / 10 000   high


   Aegis Validation Report
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Metric              ┃ Value                         ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Rules checked       │ 3                             │
│ Passed              │ 1                             │
│ Failed              │ 2                             │
│ Pass rate           │ 33.3%                         │
│ Critical failures   │ 1                             │
│ High failures       │ 1                             │
│ LLM cost            │ $0.000412                     │
│ Run ID              │ run_20260511_143022_a1b2c3    │
└─────────────────────┴───────────────────────────────┘

LLM Diagnosis
─────────────────────────────────────────────────────────────────────
Rule:    orders_order_id_not_null  (critical)
Table:   orders
Failed:  50 rows (0.5% of 10 000)

Explanation:
  50 rows in the orders table have a NULL order_id. This is a critical
  integrity violation — downstream joins on order_id will silently drop
  these rows, causing revenue undercounting.

Likely cause:
  The ETL pipeline that loads from the source OLTP database uses an
  INSERT ... SELECT without a NOT NULL guard. When the source system
  emits a partial record (e.g. a cart-abandonment event), order_id is
  omitted and lands as NULL.

Recommended action:
  1. Run: SELECT * FROM orders WHERE order_id IS NULL LIMIT 20
  2. Check the ETL job logs for the ingestion window 2026-05-11 00:00–06:00
  3. Add a NOT NULL constraint or COALESCE guard in the staging transform

Root cause trace (OpenLineage):
  orders ← stg_orders ← raw_orders_kafka_sink (topic: orders-v2)
  Last healthy upstream checkpoint: 2026-05-10 23:58 UTC
─────────────────────────────────────────────────────────────────────

Audit trail written → ~/.aegis/history.db
Export: aegis audit trajectory run_20260511_143022_a1b2c3

Exit code: 1  (1 critical failure)
```

---

## Key features

| Feature | Detail |
|---|---|
| **7-node pipeline** | plan → execute → reconcile → classify → diagnose → rca → report |
| **28 rule types** | completeness, uniqueness, validity, referential, statistical, timeliness, volume |
| **4 warehouse adapters** | DuckDB, BigQuery, Databricks, Athena |
| **3 LLM providers** | Anthropic, OpenAI, Ollama (local/offline) |
| **Full audit trail** | Every LLM call and decision logged to SQLite with FTS5 search |
| **MCP server** | Use Aegis as a Claude tool — run checks from Claude Desktop |
| **Fine-tuning export** | `aegis audit export-dataset` dumps ShareGPT JSONL for model training |
| **Apache 2.0** | Fully open source, self-hosted, no SaaS required |

---

## How it compares

| | **Aegis** | **Great Expectations** | **Soda Core** | **Monte Carlo** | **dbt tests** |
|---|:---:|:---:|:---:|:---:|:---:|
| License | Apache 2.0 | Apache 2.0 | Apache 2.0 | Commercial | Apache 2.0 |
| Self-hosted | ✅ | ✅ | ✅ | ❌ | ✅ |
| LLM-powered diagnosis | ✅ | ❌ | ❌ | Partial | ❌ |
| Root cause analysis | ✅ | ❌ | ❌ | ✅ | ❌ |
| Audit trail | ✅ | Partial | Partial | ✅ | ❌ |
| Local LLM (Ollama) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Fine-tuning export | ✅ | ❌ | ❌ | ❌ | ❌ |
| MCP server | ✅ | ❌ | ❌ | ❌ | ❌ |

[Full comparison →](vs-competitors.md)

---

## Architecture

```
rules.yaml
    │
    ▼
  plan ──► execute ──► reconcile ──► classify ──► diagnose ──► rca ──► report
                           │                          │          │
                      28 rule types             LLM severity   LLM root
                      4 warehouses               triage        cause +
                                                               lineage
```

**Adapters**

```
LLM adapters:        Anthropic  •  OpenAI  •  Ollama (local)
Warehouse adapters:  DuckDB  •  BigQuery  •  Databricks  •  Athena
```

[Full architecture docs →](architecture.md)

---

## Install

```bash
pip install aegis-dq
```

Then follow the [5-minute quickstart →](getting-started.md)
