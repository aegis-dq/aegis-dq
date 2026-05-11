"""Report node — builds a structured report dict from all results."""

from __future__ import annotations

from datetime import UTC, datetime

from ..state import AegisState


async def report_node(state: AegisState) -> AegisState:
    """Assemble final report from results and diagnoses."""
    total = len(state["rule_results"])
    passed = sum(1 for r in state["rule_results"] if r.passed)
    failed = total - passed

    diag_map = {d["failure_id"]: d for d in state.get("diagnoses", [])}

    failure_details = []
    for f in state["failures"]:
        rid = f.rule.metadata.id
        detail: dict = {
            "rule_id": rid,
            "table": f.rule.spec_scope.table,
            "severity": f.rule.metadata.severity.value,
            "rows_failed": f.result.row_count_failed,
            "rows_checked": f.result.row_count_checked,
        }
        if f.result.error:
            detail["error"] = f.result.error
        if rid in diag_map:
            detail["diagnosis"] = diag_map[rid]
        failure_details.append(detail)

    state["report"] = {
        "run_id": state["run_id"],
        "timestamp": datetime.now(UTC).isoformat(),
        "triggered_by": state["triggered_by"],
        "summary": {
            "total_rules": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / total * 100, 1) if total else 0.0,
        },
        "failures": failure_details,
        "cost_usd": round(state.get("cost_total_usd", 0.0), 6),
        "tokens_total": state.get("tokens_total", 0),
    }
    return state
