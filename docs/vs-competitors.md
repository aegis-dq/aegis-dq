# Aegis vs the alternatives

Choosing a data quality tool comes down to four questions: does it explain *why* a check failed (diagnosis capability), what does it cost to run at scale, can you bring your own LLM or run fully offline, and is it open source so you can audit and extend it? The tools below answer those questions very differently.

---

## Full comparison

| Feature | **Aegis** | **Great Expectations** | **Soda Core** | **Monte Carlo** | **dbt tests** |
|---|:---:|:---:|:---:|:---:|:---:|
| **License** | Apache 2.0 | Apache 2.0 | Apache 2.0 | Commercial SaaS | Apache 2.0 |
| **Self-hosted** | ✅ | ✅ | ✅ | ❌ | ✅ |
| **LLM-powered diagnosis** | ✅ | ❌ | ❌ | Partial (proprietary) | ❌ |
| **Root cause analysis** | ✅ (lineage-aware) | ❌ | ❌ | ✅ (proprietary) | ❌ |
| **ML anomaly detection** | ✅ zscore, isolation forest, learned threshold | ❌ | ❌ | Partial (proprietary) | ❌ |
| **Audit trail (every decision logged)** | ✅ SQLite + FTS5 | Partial (run docs) | Partial (scan results) | ✅ (proprietary) | ❌ |
| **Pluggable LLM (bring your own)** | ✅ Anthropic / OpenAI / Ollama / Bedrock | ❌ | ❌ | ❌ | ❌ |
| **Local LLM (Ollama / fully offline)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Warehouse support** | DuckDB, BigQuery, Databricks, Athena | 20+ (Great Expectations Cloud) | 10+ | 15+ | dbt-supported only |
| **dbt integration** | ✅ manifest parser | ✅ native | ✅ | ✅ | ✅ native |
| **Airflow integration** | ✅ AegisOperator | ✅ | ✅ | ✅ | ✅ |
| **MCP server (Claude tool use)** | ✅ 5 tools | ❌ | ❌ | ❌ | ❌ |
| **Fine-tuning data export** | ✅ ShareGPT JSONL | ❌ | ❌ | ❌ | ❌ |
| **Python install** | `pip install aegis-dq` | `pip install great-expectations` | `pip install soda-core` | Agent install | `pip install dbt-core` |
| **YAML rule format** | ✅ Kubernetes-style CRD | Partial (JSON/Python) | ✅ | UI-driven | YAML (dbt schema.yml) |
| **Pricing** | Free / open source | Free + paid Cloud | Free + paid Cloud | $$$  enterprise | Free / open source |

---

## When to choose each tool

### Choose Aegis when:

- You want to know **why** a check failed, not just that it did — Aegis gives you an LLM-written diagnosis with a root cause and a concrete action for every failure.
- You need a **full, searchable audit trail** of every validation decision, LLM call, and cost — useful for regulated industries and debugging.
- You want to run **completely offline or cloud-native** — Ollama for zero-cost local inference, or AWS Bedrock for no-API-key usage with your existing AWS credentials profile.
- You are building **tooling on top of a DQ framework** — the MCP server lets Claude Desktop run checks, and the ShareGPT export lets you fine-tune a model on your own diagnostic reasoning.
- You want **YAML-first rules** that look like Kubernetes CRDs and are easy to version-control and code-review.
- You want **statistical and ML-based anomaly detection** without hard-coding thresholds — `zscore_outlier`, `isolation_forest`, and `learned_threshold` rules learn from historical runs stored in `~/.aegis/history.db`.

### Choose Great Expectations when:

- Your team already has an established GE codebase and expectation suites and the migration cost outweighs the benefit of LLM diagnosis.
- You need the broadest warehouse coverage and are willing to use GE Cloud for the managed experience.
- You prefer a Python-native API (`expect_column_values_to_not_be_null(...)`) over YAML.

### Choose Soda when:

- Your team wants a **managed SaaS offering** with enterprise support contracts and an SLA.
- You need business-user-facing UI for non-engineers to write checks without touching YAML or Python.
- You are already using the Soda ecosystem for data observability across multiple platforms.

### Choose Monte Carlo when:

- You need **enterprise-scale data observability** with catalog integration, table health scores, and anomaly detection across a large warehouse estate.
- You have budget for a commercial platform and want vendor-supported root cause analysis built into the product.
- Your primary concern is proactive anomaly detection rather than rule-based validation.

### Choose dbt tests when:

- You just need **simple pass/fail assertions** co-located with your dbt models and you have no need for LLM diagnosis or audit trails.
- Your entire data transformation stack lives in dbt and you want the smallest possible footprint.
- You want tests that run automatically as part of `dbt build` with no additional infrastructure.
