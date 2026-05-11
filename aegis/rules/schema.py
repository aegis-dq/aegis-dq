"""Pydantic v2 models for Aegis rule schema."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class RuleType(StrEnum):
    SQL_EXPRESSION = "sql_expression"
    NOT_NULL = "not_null"
    UNIQUE = "unique"
    ROW_COUNT = "row_count"
    FRESHNESS = "freshness"
    CUSTOM_SQL = "custom_sql"


class RuleScope(BaseModel):
    warehouse: str = "duckdb"
    database: str | None = None
    schema_name: str | None = Field(None, alias="schema")  # 'schema' is reserved
    table: str
    columns: list[str] = []

    model_config = {"populate_by_name": True}


class RuleLogic(BaseModel):
    type: RuleType
    expression: str | None = None  # SQL WHERE clause (rows that PASS)
    query: str | None = None  # full custom SQL — must return (passed: bool, row_count: int)
    threshold: float | None = None  # for row_count, freshness
    unit: str | None = None  # "hours", "rows", etc.


class ReconciliationConfig(BaseModel):
    source_table: str
    source_column: str
    transform: str | None = None
    tolerance: float = 0.0


class DiagnosisHints(BaseModel):
    common_causes: list[str] = []
    lineage_hints: dict[str, list[str]] = {}


class RemediationConfig(BaseModel):
    auto_remediate: bool = False
    proposal_strategy: Literal["llm_with_lineage", "llm_simple", "none"] = "llm_simple"


class SLAConfig(BaseModel):
    detection_window: str = "1h"
    notification_target: str | None = None


class RuleMetadata(BaseModel):
    id: str
    domain: str | None = None
    severity: Severity = Severity.MEDIUM
    owner: str | None = None
    tags: list[str] = []
    description: str | None = None


class DataQualityRule(BaseModel):
    api_version: str = Field("aegis.dev/v1", alias="apiVersion")
    kind: str = "DataQualityRule"
    metadata: RuleMetadata
    spec_scope: RuleScope = Field(..., alias="scope")
    spec_logic: RuleLogic = Field(..., alias="logic")
    reconciliation: ReconciliationConfig | None = None
    diagnosis: DiagnosisHints = Field(default_factory=DiagnosisHints)
    remediation: RemediationConfig = Field(default_factory=RemediationConfig)
    sla: SLAConfig = Field(default_factory=SLAConfig)

    model_config = {"populate_by_name": True}


class RuleResult(BaseModel):
    rule_id: str
    passed: bool
    row_count_checked: int = 0
    row_count_failed: int = 0
    failure_sample: list[dict[str, Any]] = []
    error: str | None = None
    duration_ms: float = 0.0


class RuleFailure(BaseModel):
    rule: DataQualityRule
    result: RuleResult
