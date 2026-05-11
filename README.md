# Aegis

**Open, audit-grade agentic data quality framework with portable industry packs.**

Aegis combines LangGraph-orchestrated agents with Pydantic-validated rules and pluggable warehouse adapters to continuously validate, diagnose, and report on data quality — with every decision traceable and every cost metered.

## Install

```bash
pip install aegis-dq
# or, for development:
git clone https://github.com/your-org/aegis-dq && cd aegis-dq
pip install -e ".[dev]"
```

## Quickstart

```bash
# 1. Generate an example rules file
aegis init

# 2. Edit rules.yaml to match your tables and checks
$EDITOR rules.yaml

# 3. Run validation (uses :memory: DuckDB by default)
aegis run rules.yaml

# 4. Point at a real DuckDB file and write a JSON report
aegis run rules.yaml --db ./warehouse.duckdb --output-json report.json

# 5. Skip LLM diagnosis (no API key needed)
aegis run rules.yaml --no-llm
```

Set `ANTHROPIC_API_KEY` in your environment to enable LLM-powered diagnosis.

## Architecture

```
 ┌─────────────────────────────────────────────────┐
 │                  AegisAgent                      │
 │                 (LangGraph)                      │
 │                                                  │
 │  ┌────────┐  ┌─────────┐  ┌──────────┐  ┌────┐ │
 │  │  plan  │→ │ execute │→ │ diagnose │→ │    │ │
 │  │        │  │         │  │  (LLM)   │  │rep.│ │
 │  └────────┘  └─────────┘  └──────────┘  └────┘ │
 └──────┬──────────────┬──────────────────────┬────┘
        │              │                      │
   YAML rules    DuckDB adapter         SQLite history
   (Pydantic)    (WarehouseAdapter)     (~/.aegis/)
```

## Rule format

```yaml
rules:
  - apiVersion: aegis.dev/v1
    kind: DataQualityRule
    metadata:
      id: orders_no_nulls
      severity: critical        # critical | high | medium | low | info
      domain: retail
      owner: data-platform
      tags: [completeness]
    scope:
      warehouse: duckdb
      table: orders
      columns: [order_id]
    logic:
      type: not_null            # not_null | unique | row_count | sql_expression | custom_sql | freshness
    diagnosis:
      common_causes:
        - "ETL pipeline failed mid-load"
```

## License

Apache-2.0
