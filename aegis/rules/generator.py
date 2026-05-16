"""LLM-based DQ rule generation from table schema + optional KB context."""

from __future__ import annotations

import re

import yaml

_SYSTEM_PROMPT = """\
You are a senior data quality engineer and fraud/compliance analyst. Given a table \
schema and optional business context, generate comprehensive Aegis data quality rules \
as valid YAML.

Supported rule types:
  Completeness and schema:
    not_null, not_empty_string, column_exists, null_percentage_below,
    conditional_not_null

  Uniqueness:
    unique, composite_unique, duplicate_percentage_below

  Numeric, statistical, and anomaly checks:
    between, min_value_check, max_value_check, mean_between, stddev_below,
    column_sum_between, zscore_outlier, isolation_forest, learned_threshold

  Categorical and string checks:
    accepted_values, not_accepted_values, regex_match

  Temporal and volume checks:
    row_count, row_count_between, freshness, no_future_dates, date_order

  Referential integrity and reconciliation:
    foreign_key, reconcile_row_count, reconcile_column_sum, reconcile_key_match

  SQL checks:
    sql_expression, custom_sql

SQL rule guidance:
  sql_expression:
    - expression is a WHERE clause fragment — rows matching it PASS (are valid)
    - No JOINs, subqueries, CTEs, or window functions
    - Example: "amount > 0 AND status != 'unknown'"

  custom_sql:
    - Full SELECT query returning rows that FAIL (violating rows)
    - Use for: JOINs to other tables, CTEs, window functions, aggregations,
      velocity checks, concentration ratios, referential integrity
    - Must return at least one identifying column (e.g. account_id, txn_id)
    - Example:
        SELECT t.txn_id, t.account_id, t.amount_usd
        FROM transactions t
        LEFT JOIN compliance_flags cf ON cf.txn_id = t.txn_id AND cf.flag_type = 'CTR'
        WHERE t.amount_usd >= 10000 AND cf.flag_id IS NULL

Column and logic field placement rules (CRITICAL - wrong placement causes execution errors):
- Put primary column checks in scope.columns, not in logic.
- For not_null, not_empty_string, unique, column_exists, no_future_dates,
  composite_unique: put the checked column(s) in scope.columns.
- For accepted_values and not_accepted_values: put the checked column in
  scope.columns and the allowed/prohibited list in logic.values.
- For between, mean_between, column_sum_between: put the checked column in
  scope.columns and set logic.min_value and logic.max_value.
- For row_count_between: set logic.min_value and logic.max_value; no column
  is required.
- For min_value_check and max_value_check: put the checked column in
  scope.columns and set logic.min_value or logic.max_value.
- For regex_match: put the checked column in scope.columns and set
  logic.pattern.
- For null_percentage_below, duplicate_percentage_below, stddev_below,
  row_count: set logic.threshold. Use scope.columns for column-based checks.
- For freshness: set logic.threshold and logic.unit (for example, hours).
- For foreign_key: put the local key column in scope.columns and set
  logic.reference_table and logic.reference_column.
- For conditional_not_null: put the required column in scope.columns and set
  logic.condition to the SQL condition that makes it required.
- For date_order: put the first/earlier date column in scope.columns and the
  second/later date column in logic.column_b.
- For reconcile_row_count: set the target table in scope.table and
  logic.source_table.
- For reconcile_column_sum and reconcile_key_match: set the target table in
  scope.table, the compared column/key in scope.columns, and
  logic.source_table. Use logic.tolerance_pct only when a tolerance is needed.
- For zscore_outlier and learned_threshold: put the metric column in
  scope.columns and set logic.zscore_threshold when a non-default cutoff is
  needed. For learned_threshold, set logic.min_history_days if required.
- For isolation_forest: put the metric column in scope.columns and set
  logic.contamination when a non-default anomaly fraction is needed.
- For sql_expression: put expression in logic.expression (no columns needed in scope)
- For custom_sql: put full SELECT query in logic.query (no columns in scope)

Metadata requirements per rule:
- id: snake_case, format {table}_{column_or_concept}_{check}
- severity: critical | high | medium | low | info
- version: "1.0.0"
- status: draft

Output ONLY a YAML code block in this exact format:
```yaml
rules:
  - apiVersion: aegis.dev/v1
    kind: DataQualityRule
    metadata:
      id: transactions_amount_not_null
      severity: critical
      version: "1.0.0"
      status: draft
    scope:
      table: transactions
      columns: [amount_usd]
    logic:
      type: not_null

  - apiVersion: aegis.dev/v1
    kind: DataQualityRule
    metadata:
      id: transactions_status_valid_values
      severity: high
      version: "1.0.0"
      status: draft
    scope:
      table: transactions
      columns: [status]
    logic:
      type: accepted_values
      values: [pending, settled, reversed, flagged]

  - apiVersion: aegis.dev/v1
    kind: DataQualityRule
    metadata:
      id: transactions_amount_positive
      severity: critical
      version: "1.0.0"
      status: draft
    scope:
      table: transactions
    logic:
      type: sql_expression
      expression: "amount_usd > 0"

  - apiVersion: aegis.dev/v1
    kind: DataQualityRule
    metadata:
      id: transactions_ctr_filing_required
      severity: critical
      version: "1.0.0"
      status: draft
    scope:
      table: transactions
    logic:
      type: custom_sql
      query: |
        SELECT t.txn_id, t.account_id, t.amount_usd
        FROM transactions t
        LEFT JOIN compliance_flags cf ON cf.txn_id = t.txn_id AND cf.flag_type = 'CTR'
        WHERE t.amount_usd >= 10000 AND cf.flag_id IS NULL
```
No explanation. No extra text outside the YAML block.\
"""

_NUMERIC_TYPES = {
    "integer",
    "int",
    "bigint",
    "double",
    "float",
    "decimal",
    "real",
    "numeric",
    "hugeint",
    "ubigint",
    "uinteger",
    "smallint",
    "tinyint",
}


def introspect_table(conn, table: str) -> dict:
    """Return schema + basic stats for *table* using a DuckDB connection."""
    try:
        rows = conn.execute(f"DESCRIBE {table}").fetchall()
    except Exception:
        return {"table": table, "row_count": 0, "columns": []}

    try:
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except Exception:
        row_count = 0

    columns: list[dict] = []
    for row in rows:
        col_name = row[0]
        col_type = row[1]
        col_info: dict = {
            "name": col_name,
            "type": col_type,
            "null_count": 0,
            "distinct_count": 0,
            "min": None,
            "max": None,
        }
        try:
            stats = conn.execute(
                f"SELECT COUNT(*) - COUNT({col_name}), COUNT(DISTINCT {col_name}) FROM {table}"
            ).fetchone()
            col_info["null_count"] = stats[0]
            col_info["distinct_count"] = stats[1]
        except Exception:
            pass

        base_type = col_type.lower().split("(")[0].strip()
        if base_type in _NUMERIC_TYPES and row_count > 0:
            try:
                mn, mx = conn.execute(
                    f"SELECT MIN({col_name}), MAX({col_name}) FROM {table}"
                ).fetchone()
                col_info["min"] = float(mn) if mn is not None else None
                col_info["max"] = float(mx) if mx is not None else None
            except Exception:
                pass

        columns.append(col_info)

    return {"table": table, "row_count": row_count, "columns": columns}


def _build_user_prompt(schema_info: dict, max_rules: int, kb_text: str | None) -> str:
    table = schema_info["table"]
    row_count = schema_info.get("row_count", 0)
    lines = [f"Table: {table}", f"Row count: {row_count}", "", "Columns:"]
    for col in schema_info.get("columns", []):
        stat = f"nulls={col['null_count']}, distinct={col['distinct_count']}"
        if col["min"] is not None:
            stat += f", min={col['min']}, max={col['max']}"
        lines.append(f"  - {col['name']} ({col['type']}): {stat}")
    lines.append(f"\nGenerate up to {max_rules} targeted data quality rules.")
    if kb_text:
        lines += [
            "\nBusiness context / validation rules:",
            "---",
            kb_text[:12000],
            "---",
        ]
    return "\n".join(lines)


def _extract_yaml(text: str) -> str:
    """Strip ```yaml ... ``` fences; return raw YAML string."""
    m = re.search(r"```(?:yaml)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def _parse_yaml_rules(yaml_text: str) -> list[dict]:
    try:
        doc = yaml.safe_load(yaml_text)
        if isinstance(doc, dict) and "rules" in doc:
            rules = doc["rules"]
            return rules if isinstance(rules, list) else []
        return []
    except Exception:
        return []


def _stamp_metadata(rules: list[dict], model_id: str) -> list[dict]:
    """Ensure version, status, generated_by are set on each rule's metadata dict."""
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        meta = rule.setdefault("metadata", {})
        meta.setdefault("version", "1.0.0")
        meta.setdefault("status", "draft")
        meta["generated_by"] = model_id
    return rules


async def generate_rules(
    table: str,
    schema_info: dict,
    llm,
    kb_text: str | None = None,
    max_rules: int = 20,
) -> tuple[str, list[dict]]:
    """Call the LLM and return (raw_yaml_string, list_of_parsed_rule_dicts).

    raw_yaml_string: ready to write to a file (YAML doc with 'rules:' key).
    list_of_parsed_rule_dicts: parsed rules (may be empty on LLM/parse failure).
    """
    user = _build_user_prompt(schema_info, max_rules, kb_text)
    text, _in_tok, _out_tok = await llm.complete(_SYSTEM_PROMPT, user, max_tokens=4096)

    model_id = getattr(llm, "_model", "llm/unknown")
    raw_yaml = _extract_yaml(text)
    rules = _parse_yaml_rules(raw_yaml)
    _stamp_metadata(rules, model_id)

    if rules:
        # Re-serialise so stamped metadata is reflected in the output file
        raw_yaml = yaml.dump({"rules": rules}, default_flow_style=False, allow_unicode=True)

    return raw_yaml, rules
