"""LLM-based DQ rule generation from table schema + optional KB context."""
from __future__ import annotations

import re

import yaml

_SYSTEM_PROMPT = """\
You are a senior data quality engineer. Given a table schema and optional business \
context, generate comprehensive Aegis data quality rules as valid YAML.

Supported rule types (use ONLY these):
not_null, unique, between, accepted_values, not_accepted_values, regex_match,
sql_expression, null_percentage_below, row_count_between, column_sum_between, mean_between

SQL rules:
- sql_expression: expression is a WHERE clause — rows that PASS (not fail)
- Do not use custom_sql

Metadata requirements per rule:
- id: snake_case, format {table}_{column}_{check}  (e.g. orders_amount_positive)
- severity: critical | high | medium | low | info
- version: "1.0.0"
- status: draft

Output ONLY a YAML code block in this exact format:
```yaml
rules:
  - apiVersion: aegis.dev/v1
    kind: DataQualityRule
    metadata:
      id: ...
      severity: high
      version: "1.0.0"
      status: draft
    scope:
      table: TABLE_NAME
    logic:
      type: not_null
```
No explanation. No extra text outside the YAML block.\
"""

_NUMERIC_TYPES = {
    "integer", "int", "bigint", "double", "float", "decimal",
    "real", "numeric", "hugeint", "ubigint", "uinteger", "smallint", "tinyint",
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
            kb_text[:4000],
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
    text, _in_tok, _out_tok = await llm.complete(_SYSTEM_PROMPT, user, max_tokens=2048)

    model_id = getattr(llm, "_model", "llm/unknown")
    raw_yaml = _extract_yaml(text)
    rules = _parse_yaml_rules(raw_yaml)
    _stamp_metadata(rules, model_id)

    if rules:
        # Re-serialise so stamped metadata is reflected in the output file
        raw_yaml = yaml.dump({"rules": rules}, default_flow_style=False, allow_unicode=True)

    return raw_yaml, rules
