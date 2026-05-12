# Getting Started

Get from zero to a working data quality pipeline in 5 minutes. No cloud account required — everything runs locally with DuckDB.

---

## 1. Install

```bash
pip install aegis-dq
```

Verify:

```bash
aegis --help
```

You should see the `init`, `validate`, `run`, `audit`, and `rules` commands listed.

---

## 2. Seed demo data

Create a local DuckDB file with 10 000 orders and intentional data quality issues baked in:

```python
# seed.py
import duckdb

con = duckdb.connect("demo.db")

con.execute("""
    CREATE TABLE orders AS
    SELECT
        i          AS order_id,
        'placed'   AS status,
        i * 9.99   AS revenue
    FROM range(1, 10001) t(i)
""")

# Inject nulls: every 200th order loses its order_id
con.execute("UPDATE orders SET order_id = NULL WHERE order_id % 200 = 0")

# Inject negatives: every 500th order has negative revenue
con.execute("UPDATE orders SET revenue = -5.00 WHERE order_id % 500 = 0")

con.close()
print("Created demo.db  (10 000 rows, 50 null order_ids, 20 negative revenues)")
```

```bash
python seed.py
# Created demo.db  (10 000 rows, 50 null order_ids, 20 negative revenues)
```

> DuckDB ships as a Python wheel — no separate install needed.

---

## 3. Create rules.yaml

Paste this into `rules.yaml` in your working directory:

```yaml
rules:

  - apiVersion: aegis.dev/v1
    kind: DataQualityRule
    metadata:
      id: orders_order_id_not_null
      severity: critical
      domain: retail
      owner: data-platform
      description: Every order must have an order_id
    scope:
      warehouse: duckdb
      table: orders
      columns: [order_id]
    logic:
      type: not_null
    diagnosis:
      common_causes:
        - ETL pipeline failed mid-load
        - Source system sent partial records

  - apiVersion: aegis.dev/v1
    kind: DataQualityRule
    metadata:
      id: orders_revenue_positive
      severity: high
      domain: retail
      owner: revenue-team
      description: Revenue must be non-negative
    scope:
      warehouse: duckdb
      table: orders
    logic:
      type: sql_expression
      expression: "revenue >= 0"
    diagnosis:
      common_causes:
        - Refund logic inverted the sign
        - Currency conversion failure

  - apiVersion: aegis.dev/v1
    kind: DataQualityRule
    metadata:
      id: orders_minimum_rows
      severity: medium
      domain: retail
      description: Orders table must have at least 1 000 rows
    scope:
      warehouse: duckdb
      table: orders
    logic:
      type: row_count
      threshold: 1000
```

---

## 4. Validate syntax offline

Before touching any data, confirm your rules are correctly formed:

```bash
aegis validate rules.yaml
```

Expected output:

```
Aegis validate — rules.yaml

  ✓ orders_order_id_not_null
  ✓ orders_revenue_positive
  ✓ orders_minimum_rows

All 3 rule(s) valid.
```

Errors (`✗`) must be fixed before running. Warnings (`⚠`) are informational and do not block execution.

---

## 5. Run without LLM

Run your rules against the demo database in offline mode — no API key needed:

```bash
aegis run rules.yaml --db demo.db --no-llm
```

Expected output:

```
Aegis DQ — loading rules from rules.yaml
Loaded 3 rules  •  warehouse: duckdb  •  llm: disabled

Running pipeline: plan → execute → reconcile → classify → diagnose → rca → report

  ✓  orders_minimum_rows          passed    10 000 rows
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
│ LLM cost            │ $0.000000                     │
└─────────────────────┴───────────────────────────────┘

Exit code: 1  (failures detected)
```

The process exits with code `1` whenever any rule fails — useful for blocking CI pipelines.

---

## 6. Run with LLM diagnosis

Set your Anthropic API key and re-run. The `diagnose` and `rca` nodes will now call the LLM for each failure:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
aegis run rules.yaml --db demo.db
```

**AWS Bedrock (no API key — uses AWS credentials profile):**

```bash
# Uses the Bedrock Converse API with Amazon Nova Pro (no use-case form needed)
python demo/realworld_demo.py --aws-profile your-aws-profile
```

Expected output (additional LLM section appended after the summary table):

```
LLM Diagnosis
─────────────────────────────────────────────────────────────────────
Rule:    orders_order_id_not_null  (critical)
Table:   orders
Failed:  50 rows (0.5% of 10 000)

Explanation:
  50 rows in the orders table have a NULL order_id. Downstream joins
  on order_id will silently drop these rows, causing undercounting in
  revenue reports.

Likely cause:
  The ETL pipeline loads from the source OLTP database without a
  NOT NULL guard. When the source emits a partial record (e.g. a
  cart-abandonment event), order_id is omitted and lands as NULL.

Recommended action:
  1. Run: SELECT * FROM orders WHERE order_id IS NULL LIMIT 20
  2. Check ETL logs for the most recent ingestion window
  3. Add a NOT NULL constraint or COALESCE guard in staging
─────────────────────────────────────────────────────────────────────
Rule:    orders_revenue_positive  (high)
Table:   orders
Failed:  20 rows (0.2% of 10 000)

Explanation:
  20 rows have revenue = -5.00, violating the non-negative revenue
  constraint.

Likely cause:
  Refund processing logic may have inverted the sign rather than
  recording refunds in a separate table.

Recommended action:
  1. Run: SELECT * FROM orders WHERE revenue < 0 LIMIT 20
  2. Verify refund handling in the ETL transform
─────────────────────────────────────────────────────────────────────

LLM cost: $0.000412  (claude-haiku-4-5, 2 diagnoses)
```

---

## 7. Use a local LLM (no API key)

If you have [Ollama](https://ollama.com) running locally, you can run diagnosis entirely offline:

```bash
# requires ollama running locally with llama3.2 pulled
aegis run rules.yaml --db demo.db --llm ollama --llm-model llama3.2
```

Ollama runs on `http://localhost:11434` by default. To use a different host:

```bash
aegis run rules.yaml --db demo.db --llm ollama --llm-model llama3.2 \
  --llm-base-url http://my-ollama-host:11434
```

---

## 8. Inspect the audit trail

Every run writes to `~/.aegis/history.db`. Use the `audit` subcommands to explore it:

```bash
# List all runs (newest first)
aegis audit list-runs

# Show the full node-by-node trajectory for a specific run
aegis audit trajectory run_20260511_143022_a1b2c3

# Full-text search across all LLM decisions
aegis audit search "null order_id"
```

Example `list-runs` output:

```
  run_id                           started              rules  passed  failed
  run_20260511_143022_a1b2c3      2026-05-11 14:30:22      3       1       2
  run_20260510_091500_d4e5f6      2026-05-10 09:15:00      3       3       0
```

---

## 9. Export for fine-tuning

Dump the audit trail for a run as ShareGPT-format JSONL, ready for supervised fine-tuning:

```bash
aegis audit export-dataset output.jsonl --run-id run_20260511_143022_a1b2c3
```

Omit `--run-id` to export all runs:

```bash
aegis audit export-dataset output.jsonl
```

Each line in `output.jsonl` is one conversation turn: the rule context as a user message and the LLM diagnosis as an assistant message.

---

## 10. Real-world end-to-end demo

The repository ships a complete RetailCo e-commerce demo that exercises every pipeline node against a 4-table DuckDB database with realistic dirty data. Use it to see the full agentic output — diagnosis, root-cause analysis, and LLM-generated remediation SQL — in one command.

```bash
# Validation only (no LLM, instant)
python demo/realworld_demo.py --no-llm

# Full pipeline with AWS Bedrock (requires ~/.aws/credentials profile)
python demo/realworld_demo.py --aws-profile your-profile

# Full pipeline with Anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python demo/realworld_demo.py --no-llm   # swap in AnthropicAdapter in the script
```

What runs:
- **4 tables** — customers, products, orders, payments (10 rows each, dirty data injected)
- **12 rules** — not_null, not_empty_string, accepted_values, sql_expression, unique, min_value_check, foreign_key, date_order
- **11 failures** detected: NULL email, empty email, invalid tier, negative price, duplicate SKU, negative stock, orphan FK, date inversion, invalid status, orphan payment, negative payment
- **Full LLM output** per failure: explanation + likely_cause + suggested_action + root_cause + propagation + fix + proposed SQL
- **Run time**: ~7s | **LLM cost**: ~$0.006 (Amazon Nova Pro) | **Tokens**: ~3,600

The demo script is at [`demo/realworld_demo.py`](../demo/realworld_demo.py).

---

## 11. Next steps

- [Rule Schema Reference](rule-schema-reference.md) — all 28 rule types with full field definitions
- [Architecture](architecture.md) — deep dive into the 7-node pipeline
- [dbt Integration](integrations/dbt.md) — auto-generate Aegis rules from your dbt manifest
- [Airflow Integration](integrations/airflow.md) — run Aegis as an Airflow operator
- [MCP Server](integrations/mcp.md) — use Aegis as a Claude Desktop tool
- [vs Competitors](vs-competitors.md) — how Aegis compares to Great Expectations, Soda, and Monte Carlo
