"""Diagnose node — uses LLM to explain each rule failure."""

from __future__ import annotations

import asyncio

from ...adapters.llm.base import LLMAdapter
from ..state import AegisState, Diagnosis

SYSTEM_PROMPT = """You are a senior data engineer performing data quality diagnosis.
Given a failed data quality rule, explain:
1. What the failure means in plain English
2. The most likely root cause
3. A concrete next step to investigate or fix it

Be concise (3-5 sentences total). Output in this exact format:
EXPLANATION: <one sentence>
LIKELY_CAUSE: <one sentence>
SUGGESTED_ACTION: <one sentence>"""


async def diagnose_node(state: AegisState, llm: LLMAdapter | None) -> AegisState:
    """Diagnose each failure using the LLM. Skips gracefully if llm is None."""
    if not state["failures"] or llm is None:
        state["diagnoses"] = []
        return state

    async def diagnose_one(failure) -> tuple[Diagnosis, int, int]:
        rule = failure.rule
        result = failure.result
        sample_str = (
            str(result.failure_sample[:3]) if result.failure_sample else "No sample available"
        )

        user_msg = f"""Rule: {rule.metadata.id}
Table: {rule.spec_scope.table}
Rule type: {rule.spec_logic.type}
Expression: {rule.spec_logic.expression or rule.spec_logic.query or "N/A"}
Rows checked: {result.row_count_checked}
Rows failed: {result.row_count_failed}
Failure sample: {sample_str}
Common causes hint: {", ".join(rule.diagnosis.common_causes) if rule.diagnosis.common_causes else "None provided"}
Error: {result.error or "None"}"""

        text, in_tok, out_tok = await llm.complete(SYSTEM_PROMPT, user_msg, max_tokens=512)

        lines = {
            line.split(": ", 1)[0]: line.split(": ", 1)[1]
            for line in text.strip().splitlines()
            if ": " in line
        }

        diag: Diagnosis = {
            "failure_id": rule.metadata.id,
            "explanation": lines.get("EXPLANATION", text[:200]),
            "likely_cause": lines.get("LIKELY_CAUSE", "Unknown"),
            "suggested_action": lines.get("SUGGESTED_ACTION", "Investigate manually"),
        }
        return diag, in_tok, out_tok

    tasks = [diagnose_one(f) for f in state["failures"]]
    outcomes = await asyncio.gather(*tasks)

    diagnoses: list[Diagnosis] = []
    total_in, total_out = 0, 0
    for diag, in_tok, out_tok in outcomes:
        diagnoses.append(diag)
        total_in += in_tok
        total_out += out_tok

    # claude-haiku-4-5 pricing: $0.80/M input, $4.00/M output
    cost = (total_in * 0.80 + total_out * 4.00) / 1_000_000

    state["diagnoses"] = diagnoses
    state["cost_total_usd"] = state.get("cost_total_usd", 0.0) + cost
    state["tokens_total"] = state.get("tokens_total", 0) + total_in + total_out
    return state
