# Aegis

**Open, audit-grade agentic data quality framework — LLM-powered diagnosis, full audit trail, runs everywhere.**

Aegis orchestrates a **5-node LangGraph pipeline** that validates your data, diagnoses failures with an LLM, traces root causes through your lineage graph, and logs every decision to a searchable audit trail — all from a single YAML file.

[Get Started in 5 minutes](getting-started.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/aegis-dq/aegis-dq){ .md-button }

---

## See it in action

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

Failures by Severity
  ● CRITICAL (6)  customers_email_not_null · orders_amount_positive
                  orders_customer_fk · payments_order_fk
                  products_price_positive · products_sku_unique
  ● HIGH     (4)  customers_email_not_empty · orders_date_order
                  orders_status_valid · products_stock_non_negative
  ● MEDIUM   (1)  customers_tier_accepted

LLM Diagnoses
  orders_customer_fk  →  Order placed with customer_id=99 that does not exist.
                         Likely cause: customer deleted or test record not cleaned up.

Remediation SQL (LLM-generated)
  orders_status_valid          UPDATE orders SET status = 'SHIPPED' WHERE status = 'DISPATCHED';
  products_price_positive      UPDATE products SET price = ABS(price) WHERE price < 0;
  products_stock_non_negative  UPDATE products SET stock_quantity = 0 WHERE stock_quantity < 0;
```

---

## Key features

| Feature | Detail |
|---|---|
| **5-node pipeline** | plan → parallel_table → reconcile → remediate → report (tables run concurrently) |
| **31 rule types** | completeness, uniqueness, validity, referential, statistical, timeliness, volume, ML anomaly |
| **6 warehouse adapters** | DuckDB, Postgres/Redshift, BigQuery, Databricks, Athena, Snowflake |
| **4 LLM providers** | Anthropic Claude, OpenAI, Ollama (local/offline), AWS Bedrock |
| **SQL verification** | 3-stage pipeline — syntax, schema-aware, dry-run — with LLM self-correction |
| **Rule versioning** | `version`, `status` (draft/active/deprecated), `generated_by` on every rule |
| **LLM rule generation** | `aegis generate TABLE --db path --kb policy.md` — schema-aware structural rules + business validation rules from a KB document |
| **Full audit trail** | Every LLM call and decision logged to SQLite with FTS5 search |
| **GitHub Action** | CI/CD gate — fails the job when rules fail, outputs pass-rate and report JSON |
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
| SQL auto-fix proposals | ✅ | ❌ | ❌ | ❌ | ❌ |
| LLM rule generation | ✅ | ❌ | ❌ | ❌ | ❌ |
| ML anomaly detection | ✅ | ❌ | ❌ | ✅ | ❌ |
| Audit trail | ✅ | Partial | Partial | ✅ | ❌ |
| Local LLM (Ollama) | ✅ | ❌ | ❌ | ❌ | ❌ |
| AWS Bedrock | ✅ | ❌ | ❌ | ❌ | ❌ |
| GitHub Action | ✅ | ❌ | Partial | ❌ | ✅ |
| Fine-tuning export | ✅ | ❌ | ❌ | ❌ | ❌ |
| MCP server | ✅ | ❌ | ❌ | ❌ | ❌ |

[Full comparison →](vs-competitors.md)

---

## Architecture

```
rules.yaml
    │
    ▼
  plan ──► parallel_table ──► reconcile ──► remediate ──► report
                 │
         ┌──────────────────┐
         │  per table:      │
         │  execute         │
         │  classify        │
         │  diagnose        │
         │  rca             │
         └──────────────────┘
```

**Adapters**

```
LLM adapters:        Anthropic  •  OpenAI  •  Ollama (local)  •  AWS Bedrock
Warehouse adapters:  DuckDB  •  Postgres/Redshift  •  BigQuery  •  Databricks  •  Athena  •  Snowflake
```

[Full architecture docs →](architecture.md)

---

## Install

```bash
pip install aegis-dq
```

Then follow the [5-minute quickstart →](getting-started.md)
