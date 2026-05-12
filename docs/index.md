# Aegis

**Open, audit-grade agentic data quality framework — LLM-powered diagnosis, full audit trail, runs everywhere.**

Aegis orchestrates a **5-node LangGraph pipeline** that validates your data, diagnoses failures with an LLM, traces root causes through your lineage graph, and logs every decision to a searchable audit trail — all from a single YAML file.

[Get Started in 5 minutes](getting-started.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/aegis-dq/aegis-dq){ .md-button }

---

## See it in action

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

LLM Diagnoses ──────────────────────────────────────────
  orders_customer_fk → orders
  Explanation:  Order placed with customer_id=99 that does not exist in customers.
  Likely cause: Customer deleted or test account not cleaned up.
  Action:       Verify customer_id=99; check for recent deletions or orphan test data.

Remediation SQL ────────────────────────────────────────
  orders_status_valid        UPDATE orders SET status = 'SHIPPED' WHERE status = 'DISPATCHED';
  products_price_positive    UPDATE products SET price = ABS(price) WHERE product_id = 5 AND price < 0;
  products_stock_non_negative UPDATE products SET stock_quantity = 0 WHERE stock_quantity < 0 AND product_sku = 'SKU-010';
```

---

## Key features

| Feature | Detail |
|---|---|
| **5-node pipeline** | plan → parallel_table → reconcile → remediate → report (tables run concurrently) |
| **31 rule types** | completeness, uniqueness, validity, referential, statistical, timeliness, volume, ML anomaly |
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
Warehouse adapters:  DuckDB  •  BigQuery  •  Databricks  •  Athena
```

[Full architecture docs →](architecture.md)

---

## Install

```bash
pip install aegis-dq
```

Then follow the [5-minute quickstart →](getting-started.md)
