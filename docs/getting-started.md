# Getting Started with Aegis

This guide walks you from zero to your first data quality validation run in under 10 minutes, using a local DuckDB database — no cloud account or API key required to start.

---

## Prerequisites

- Python 3.11+
- A terminal

---

## Step 1 — Install

```bash
pip install aegis-dq
```

Verify the install:

```bash
aegis --help
```

You should see the `init`, `validate`, `run`, `rules`, and `audit` commands.

---

## Step 2 — Generate a rules file

```bash
aegis init
```

This creates `rules.yaml` in your current directory with two example rules. Open it — the format is self-explanatory YAML.

For this tutorial, use the retail example that ships with the repo:

```bash
# If you cloned the repo:
cp examples/retail_basic/rules_full.yaml rules.yaml
```

Or paste this into `rules.yaml`:

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
      description: Revenue must be >= 0
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
      description: Orders table must not be empty
    scope:
      warehouse: duckdb
      table: orders
    logic:
      type: row_count
      threshold: 1
```

---

## Step 3 — Validate syntax (offline)

Before touching any data, check that your rules are correctly formed:

```bash
aegis validate rules.yaml
```

Expected output:

```
Aegis validate — rules.yaml

  ✓ orders_order_id_not_null
  ✓ orders_revenue_positive  1 warning(s)
      ⚠  metadata.owner is not set
  ✓ orders_minimum_rows

All 3 rule(s) valid.
```

Warnings are informational — rules still run. Errors (✗) must be fixed before running.

---

## Step 4 — Create test data

Create a local DuckDB file with intentional data quality issues:

```python
# seed.py
import duckdb

con = duckdb.connect("warehouse.duckdb")
con.execute("CREATE OR REPLACE TABLE orders (order_id INT, revenue FLOAT)")
con.execute("""
    INSERT INTO orders VALUES
    (1,   100.0),
    (2,   -50.0),   -- negative revenue: will fail orders_revenue_positive
    (3,   200.0),
    (NULL, 75.0)    -- null order_id: will fail orders_order_id_not_null
""")
con.close()
print("Created warehouse.duckdb")
```

```bash
python seed.py
```

> **No DuckDB install needed** — it's bundled as a Python package.

---

## Step 5 — Run validation (offline mode)

```bash
aegis run rules.yaml --db warehouse.duckdb --no-llm
```

Expected output:

```
Aegis DQ — loading rules from rules.yaml
Loaded 3 rules

   Aegis Validation Report
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Metric        ┃ Value     ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ Rules checked │ 3         │
│ Passed        │ 1         │
│ Failed        │ 2         │
│ Pass rate     │ 33.3%     │
│ LLM cost      │ $0.000000 │
└───────────────┴───────────┘

Failures:

  orders_order_id_not_null (critical) — orders
  Rows failed: 1 / 4

  orders_revenue_positive (high) — orders
  Rows failed: 1 / 4
```

The process exits with code 1 when any rule fails — useful for CI pipelines.

---

## Step 6 — Enable LLM diagnosis

Set your API key and re-run without `--no-llm`:

```bash
# Anthropic (default)
export ANTHROPIC_API_KEY=sk-ant-...
aegis run rules.yaml --db warehouse.duckdb

# Or use OpenAI
export OPENAI_API_KEY=sk-...
aegis run rules.yaml --db warehouse.duckdb --llm openai
```

The diagnose node will now call the LLM for each failure and print:

```
  orders_revenue_positive (high) — orders
  Rows failed: 1 / 4
  Explanation: The orders table contains a row with revenue = -50.0, violating the non-negative constraint.
  Likely cause: Refund logic inverted the sign instead of using a separate refunds table.
  Action: Query SELECT * FROM orders WHERE revenue < 0 to identify affected records, then trace to the ETL job.
```

Cost for 2 diagnoses with `claude-haiku-4-5`: typically under $0.001.

---

## Step 7 — Write a JSON report

```bash
aegis run rules.yaml --db warehouse.duckdb --no-llm --output-json report.json
cat report.json
```

The report includes `run_id`, `summary`, per-failure `rows_failed`/`rows_checked`, and optionally LLM `diagnosis` for each failure. Use `run_id` to look up the audit trail later.

---

## Step 8 — Inspect the audit trail

Every run logs decisions to `~/.aegis/history.db`. View the trajectory for any run:

```bash
# Get the run_id from the JSON report, then:
aegis audit trajectory <run-id>
aegis audit trajectory <run-id> --format json
aegis audit trajectory <run-id> --format sharegpt
```

---

## Step 9 — Add Slack notifications

```bash
# Notify on any failure (default)
aegis run rules.yaml --db warehouse.duckdb \
  --notify https://hooks.slack.com/services/...

# Only notify on critical failures
aegis run rules.yaml --db warehouse.duckdb \
  --notify https://hooks.slack.com/services/... \
  --notify-on critical

# Set webhook via env var (good for CI)
export AEGIS_SLACK_WEBHOOK=https://hooks.slack.com/services/...
aegis run rules.yaml --db warehouse.duckdb
```

---

## Step 10 — Explore the built-in rule catalog

Browse 30 named rule templates:

```bash
aegis rules list
aegis rules list --category completeness
aegis rules list --json
```

Reference any template by its `type` in your rules YAML. For example, to use `email_format`:

```yaml
logic:
  type: regex_match
  pattern: '^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
```

---

## Using the retail example

The repo includes a fully-seeded retail example with 11 rules across 3 tables and intentional failures:

```bash
# Seed the database
python examples/retail_basic/seed_data.py

# Run all 11 rules
aegis run examples/retail_basic/rules_full.yaml \
  --db examples/retail_basic/retail.duckdb \
  --no-llm

# Run the demo script (same thing, programmatic)
python examples/retail_basic/demo.py
```

---

## Using Aegis from Python

```python
import asyncio
from aegis.rules.parser import load_rules
from aegis.core.agent import AegisAgent
from aegis.adapters.warehouse.duckdb import DuckDBAdapter

async def main():
    rules = load_rules("rules.yaml")
    agent = AegisAgent(
        warehouse_adapter=DuckDBAdapter("warehouse.duckdb"),
        llm_adapter=None,   # offline mode
    )
    state = await agent.run(rules, triggered_by="my_script")
    print(state["report"]["summary"])

asyncio.run(main())
```

---

## Next steps

- **Rule schema reference** — [docs/rule-schema-reference.md](rule-schema-reference.md)
- **GitHub Issues** — [track upcoming features](https://github.com/aegis-dq/aegis-dq/issues)
- **v0.5 roadmap** — RCA node, reconciliation, BigQuery, Airflow operator, retail industry pack
