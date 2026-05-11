"""LangGraph state definition for the Aegis agent."""

from __future__ import annotations

from typing import Any, TypedDict

from ..rules.schema import DataQualityRule, RuleFailure, RuleResult  # noqa: F401


class ValidationScope(TypedDict):
    tables: list[str]
    rule_ids: list[str] | None


class AgentDecision(TypedDict):
    step: str
    input_summary: str
    output_summary: str
    model: str | None
    input_tokens: int
    output_tokens: int
    duration_ms: float
    cost_usd: float


class Diagnosis(TypedDict):
    failure_id: str
    explanation: str
    likely_cause: str
    suggested_action: str


class AegisState(TypedDict):
    run_id: str
    triggered_by: str
    scope: ValidationScope
    rules: list[DataQualityRule]
    plan: list[str]  # ordered rule IDs to execute
    rule_results: list[RuleResult]
    failures: list[RuleFailure]
    classified_failures: dict[str, list[RuleFailure]]  # severity -> failures
    diagnoses: list[Diagnosis]
    report: dict[str, Any]
    trajectory: list[AgentDecision]
    cost_total_usd: float
    tokens_total: int
    error: str | None
