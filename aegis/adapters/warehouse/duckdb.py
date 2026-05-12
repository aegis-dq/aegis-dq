"""DuckDB warehouse adapter."""

from __future__ import annotations

import concurrent.futures
import threading
import time

import duckdb

from ...rules.schema import DataQualityRule, RuleResult, RuleType
from .base import WarehouseAdapter


class DuckDBAdapter(WarehouseAdapter):
    """Warehouse adapter backed by DuckDB (in-memory or file-based)."""

    def __init__(self, path: str = ":memory:"):
        self._path = path
        self._lock = threading.Lock()
        self._conn: duckdb.DuckDBPyConnection | None = None
        # Each adapter owns its thread — connection is always created and used
        # in the same thread, avoiding DuckDB cross-thread connection issues.
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="duckdb"
        )

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        with self._lock:
            if self._conn is None:
                self._conn = duckdb.connect(self._path)
        return self._conn

    async def execute_rule(self, rule: DataQualityRule) -> RuleResult:
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._execute_sync, rule)

    def _execute_sync(self, rule: DataQualityRule) -> RuleResult:  # noqa: C901
        conn = self._get_conn()
        t = rule.spec_scope.table
        logic = rule.spec_logic
        start = time.monotonic()

        try:
            if logic.type == RuleType.NOT_NULL:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                fail_count = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE {col} IS NULL"
                ).fetchone()[0]
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                sample: list[dict] = []
                if fail_count > 0:
                    sample = (
                        conn.execute(f"SELECT * FROM {t} WHERE {col} IS NULL LIMIT 5")
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=fail_count == 0,
                    row_count_checked=total,
                    row_count_failed=fail_count,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.UNIQUE:
                if not rule.spec_scope.columns:
                    raise ValueError("columns required for UNIQUE rule")
                col = rule.spec_scope.columns[0]
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                dups = conn.execute(
                    f"SELECT COUNT(*) - COUNT(DISTINCT {col}) FROM {t}"
                ).fetchone()[0]
                sample = []
                if dups > 0:
                    sample = (
                        conn.execute(
                            f"SELECT {col}, COUNT(*) as cnt FROM {t} "
                            f"GROUP BY {col} HAVING COUNT(*) > 1 LIMIT 5"
                        )
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=dups == 0,
                    row_count_checked=total,
                    row_count_failed=dups,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.SQL_EXPRESSION:
                expr = logic.expression or "TRUE"
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                fail_count = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE NOT ({expr})"
                ).fetchone()[0]
                sample = []
                if fail_count > 0:
                    sample = (
                        conn.execute(f"SELECT * FROM {t} WHERE NOT ({expr}) LIMIT 5")
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=fail_count == 0,
                    row_count_checked=total,
                    row_count_failed=fail_count,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.ROW_COUNT:
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                threshold = int(logic.threshold or 0)
                passed = total >= threshold
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=passed,
                    row_count_checked=total,
                    row_count_failed=0 if passed else 1,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.FRESHNESS:
                # Expects columns[0] to be a timestamp column.
                # Checks that max(col) is within the threshold (hours).
                if not rule.spec_scope.columns:
                    raise ValueError("columns required for FRESHNESS rule")
                col = rule.spec_scope.columns[0]
                hours = logic.threshold or 24
                result_row = conn.execute(
                    f"SELECT MAX({col}) as latest FROM {t}"
                ).fetchone()
                latest = result_row[0] if result_row else None
                if latest is None:
                    return RuleResult(
                        rule_id=rule.metadata.id,
                        passed=False,
                        error="No rows in table — cannot determine freshness",
                        duration_ms=(time.monotonic() - start) * 1000,
                    )
                age_hours = conn.execute(
                    f"SELECT DATE_DIFF('hour', MAX({col}), NOW()) FROM {t}"
                ).fetchone()[0]
                passed = float(age_hours) <= float(hours)
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=passed,
                    row_count_checked=1,
                    row_count_failed=0 if passed else 1,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.CUSTOM_SQL:
                query = logic.query or ""
                row = conn.execute(query).fetchone()
                passed = bool(row[0]) if row else False
                row_count = int(row[1]) if row and len(row) > 1 else 0
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=passed,
                    row_count_checked=row_count,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.NOT_EMPTY_STRING:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                fail_count = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE {col} IS NULL OR TRIM(CAST({col} AS VARCHAR)) = ''"
                ).fetchone()[0]
                sample = []
                if fail_count > 0:
                    sample = (
                        conn.execute(
                            f"SELECT * FROM {t} WHERE {col} IS NULL OR TRIM(CAST({col} AS VARCHAR)) = '' LIMIT 5"
                        )
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=fail_count == 0,
                    row_count_checked=total,
                    row_count_failed=fail_count,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.COMPOSITE_UNIQUE:
                if not rule.spec_scope.columns:
                    raise ValueError("columns required for COMPOSITE_UNIQUE rule")
                cols = ", ".join(rule.spec_scope.columns)
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                fail_count = conn.execute(
                    f"SELECT COALESCE(SUM(cnt - 1), 0) FROM "
                    f"(SELECT COUNT(*) as cnt FROM {t} GROUP BY {cols} HAVING COUNT(*) > 1)"
                ).fetchone()[0]
                sample = []
                if fail_count > 0:
                    sample = (
                        conn.execute(
                            f"SELECT {cols}, COUNT(*) as cnt FROM {t} GROUP BY {cols} HAVING COUNT(*) > 1 LIMIT 5"
                        )
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=fail_count == 0,
                    row_count_checked=total,
                    row_count_failed=int(fail_count),
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.BETWEEN:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                min_v = logic.min_value
                max_v = logic.max_value
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                fail_count = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE {col} IS NULL OR {col} < {min_v} OR {col} > {max_v}"
                ).fetchone()[0]
                sample = []
                if fail_count > 0:
                    sample = (
                        conn.execute(
                            f"SELECT * FROM {t} WHERE {col} IS NULL OR {col} < {min_v} OR {col} > {max_v} LIMIT 5"
                        )
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=fail_count == 0,
                    row_count_checked=total,
                    row_count_failed=fail_count,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.MIN_VALUE_CHECK:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                min_v = logic.min_value
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                fail_count = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE {col} IS NULL OR {col} < {min_v}"
                ).fetchone()[0]
                sample = []
                if fail_count > 0:
                    sample = (
                        conn.execute(
                            f"SELECT * FROM {t} WHERE {col} IS NULL OR {col} < {min_v} LIMIT 5"
                        )
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=fail_count == 0,
                    row_count_checked=total,
                    row_count_failed=fail_count,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.MAX_VALUE_CHECK:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                max_v = logic.max_value
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                fail_count = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE {col} IS NULL OR {col} > {max_v}"
                ).fetchone()[0]
                sample = []
                if fail_count > 0:
                    sample = (
                        conn.execute(
                            f"SELECT * FROM {t} WHERE {col} IS NULL OR {col} > {max_v} LIMIT 5"
                        )
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=fail_count == 0,
                    row_count_checked=total,
                    row_count_failed=fail_count,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.REGEX_MATCH:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                pattern = logic.pattern or ""
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                fail_count = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE {col} IS NULL OR NOT regexp_matches(CAST({col} AS VARCHAR), '{pattern}')"
                ).fetchone()[0]
                sample = []
                if fail_count > 0:
                    sample = (
                        conn.execute(
                            f"SELECT * FROM {t} WHERE {col} IS NULL OR NOT regexp_matches(CAST({col} AS VARCHAR), '{pattern}') LIMIT 5"
                        )
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=fail_count == 0,
                    row_count_checked=total,
                    row_count_failed=fail_count,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.ACCEPTED_VALUES:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                values_list = ", ".join(f"'{v}'" for v in (logic.values or []))
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                fail_count = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE {col} IS NOT NULL AND CAST({col} AS VARCHAR) NOT IN ({values_list})"
                ).fetchone()[0]
                sample = []
                if fail_count > 0:
                    sample = (
                        conn.execute(
                            f"SELECT * FROM {t} WHERE {col} IS NOT NULL AND CAST({col} AS VARCHAR) NOT IN ({values_list}) LIMIT 5"
                        )
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=fail_count == 0,
                    row_count_checked=total,
                    row_count_failed=fail_count,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.NOT_ACCEPTED_VALUES:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                values_list = ", ".join(f"'{v}'" for v in (logic.values or []))
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                fail_count = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE {col} IS NOT NULL AND CAST({col} AS VARCHAR) IN ({values_list})"
                ).fetchone()[0]
                sample = []
                if fail_count > 0:
                    sample = (
                        conn.execute(
                            f"SELECT * FROM {t} WHERE {col} IS NOT NULL AND CAST({col} AS VARCHAR) IN ({values_list}) LIMIT 5"
                        )
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=fail_count == 0,
                    row_count_checked=total,
                    row_count_failed=fail_count,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.FOREIGN_KEY:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                ref_table = logic.reference_table or ""
                ref_col = logic.reference_column or col
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                fail_count = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE {col} IS NOT NULL AND {col} NOT IN (SELECT {ref_col} FROM {ref_table})"
                ).fetchone()[0]
                sample = []
                if fail_count > 0:
                    sample = (
                        conn.execute(
                            f"SELECT * FROM {t} WHERE {col} IS NOT NULL AND {col} NOT IN (SELECT {ref_col} FROM {ref_table}) LIMIT 5"
                        )
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=fail_count == 0,
                    row_count_checked=total,
                    row_count_failed=fail_count,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.NULL_PERCENTAGE_BELOW:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                threshold = logic.threshold or 0.0
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                nulls = conn.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} IS NULL").fetchone()[0]
                pct = (nulls * 100.0 / total) if total > 0 else 0.0
                passed = pct <= threshold
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=passed,
                    row_count_checked=total,
                    row_count_failed=nulls,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.DUPLICATE_PERCENTAGE_BELOW:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                threshold = logic.threshold or 0.0
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                dups = conn.execute(
                    f"SELECT COUNT(*) - COUNT(DISTINCT {col}) FROM {t}"
                ).fetchone()[0]
                pct = (dups * 100.0 / total) if total > 0 else 0.0
                passed = pct <= threshold
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=passed,
                    row_count_checked=total,
                    row_count_failed=int(dups),
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.MEAN_BETWEEN:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                min_v = logic.min_value
                max_v = logic.max_value
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                mean = conn.execute(f"SELECT AVG({col}) FROM {t}").fetchone()[0]
                mean = float(mean) if mean is not None else 0.0
                passed = (min_v is None or mean >= min_v) and (max_v is None or mean <= max_v)
                sample = []
                if not passed:
                    sample = [{"mean": mean, "min_allowed": min_v, "max_allowed": max_v}]
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=passed,
                    row_count_checked=total,
                    row_count_failed=0 if passed else 1,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.STDDEV_BELOW:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                threshold = logic.threshold or 0.0
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                stddev = conn.execute(f"SELECT STDDEV({col}) FROM {t}").fetchone()[0]
                stddev = float(stddev) if stddev is not None else 0.0
                passed = stddev <= threshold
                sample = []
                if not passed:
                    sample = [{"stddev": stddev, "max_allowed": threshold}]
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=passed,
                    row_count_checked=total,
                    row_count_failed=0 if passed else 1,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.NO_FUTURE_DATES:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                fail_count = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE {col} > current_date"
                ).fetchone()[0]
                sample = []
                if fail_count > 0:
                    sample = (
                        conn.execute(f"SELECT * FROM {t} WHERE {col} > current_date LIMIT 5")
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=fail_count == 0,
                    row_count_checked=total,
                    row_count_failed=fail_count,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.ROW_COUNT_BETWEEN:
                min_v = logic.min_value or 0
                max_v = logic.max_value or float("inf")
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                passed = min_v <= total <= max_v
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=passed,
                    row_count_checked=total,
                    row_count_failed=0 if passed else 1,
                    failure_sample=[] if passed else [{"row_count": total, "min_allowed": min_v, "max_allowed": max_v}],
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.COLUMN_SUM_BETWEEN:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                min_v = logic.min_value
                max_v = logic.max_value
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                total_sum = conn.execute(f"SELECT SUM({col}) FROM {t}").fetchone()[0]
                total_sum = float(total_sum) if total_sum is not None else 0.0
                passed = (min_v is None or total_sum >= min_v) and (max_v is None or total_sum <= max_v)
                sample = []
                if not passed:
                    sample = [{"sum": total_sum, "min_allowed": min_v, "max_allowed": max_v}]
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=passed,
                    row_count_checked=total,
                    row_count_failed=0 if passed else 1,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.CONDITIONAL_NOT_NULL:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                condition = logic.condition or "TRUE"
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                fail_count = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE ({condition}) AND {col} IS NULL"
                ).fetchone()[0]
                sample = []
                if fail_count > 0:
                    sample = (
                        conn.execute(
                            f"SELECT * FROM {t} WHERE ({condition}) AND {col} IS NULL LIMIT 5"
                        )
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=fail_count == 0,
                    row_count_checked=total,
                    row_count_failed=fail_count,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.DATE_ORDER:
                col_a = rule.spec_scope.columns[0] if rule.spec_scope.columns else "*"
                col_b = logic.column_b or ""
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                fail_count = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE {col_a} IS NOT NULL AND {col_b} IS NOT NULL AND {col_a} > {col_b}"
                ).fetchone()[0]
                sample = []
                if fail_count > 0:
                    sample = (
                        conn.execute(
                            f"SELECT * FROM {t} WHERE {col_a} IS NOT NULL AND {col_b} IS NOT NULL AND {col_a} > {col_b} LIMIT 5"
                        )
                        .df()
                        .to_dict("records")
                    )
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=fail_count == 0,
                    row_count_checked=total,
                    row_count_failed=fail_count,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.COLUMN_EXISTS:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else ""
                try:
                    conn.execute(f"SELECT {col} FROM {t} LIMIT 0")
                    passed = True
                except Exception:
                    passed = False
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=passed,
                    row_count_checked=0,
                    row_count_failed=0 if passed else 1,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.RECONCILE_ROW_COUNT:
                src = logic.source_table or ""
                tol = logic.tolerance_pct / 100.0
                src_count = conn.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0]
                tgt_count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                if src_count == 0:
                    passed = tgt_count == 0
                else:
                    deviation = abs(src_count - tgt_count) / src_count
                    passed = deviation <= tol
                sample = [] if passed else [{"source_rows": src_count, "target_rows": tgt_count}]
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=passed,
                    row_count_checked=src_count,
                    row_count_failed=abs(src_count - tgt_count),
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.RECONCILE_COLUMN_SUM:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else ""
                src = logic.source_table or ""
                tol = logic.tolerance_pct / 100.0
                src_sum = conn.execute(f"SELECT COALESCE(SUM({col}), 0) FROM {src}").fetchone()[0]
                tgt_sum = conn.execute(f"SELECT COALESCE(SUM({col}), 0) FROM {t}").fetchone()[0]
                src_sum = float(src_sum)
                tgt_sum = float(tgt_sum)
                if src_sum == 0:
                    passed = tgt_sum == 0
                else:
                    deviation = abs(src_sum - tgt_sum) / abs(src_sum)
                    passed = deviation <= tol
                total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                sample = [] if passed else [{"source_sum": src_sum, "target_sum": tgt_sum, "column": col}]
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=passed,
                    row_count_checked=total,
                    row_count_failed=0 if passed else 1,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            elif logic.type == RuleType.RECONCILE_KEY_MATCH:
                col = rule.spec_scope.columns[0] if rule.spec_scope.columns else ""
                src = logic.source_table or ""
                total = conn.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0]
                missing_in_tgt = conn.execute(
                    f"SELECT COUNT(*) FROM {src} WHERE {col} NOT IN (SELECT {col} FROM {t})"
                ).fetchone()[0]
                missing_in_src = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE {col} NOT IN (SELECT {col} FROM {src})"
                ).fetchone()[0]
                passed = missing_in_tgt == 0 and missing_in_src == 0
                sample = []
                if not passed:
                    sample = [{"missing_in_target": missing_in_tgt, "missing_in_source": missing_in_src, "key_column": col}]
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=passed,
                    row_count_checked=total,
                    row_count_failed=missing_in_tgt + missing_in_src,
                    failure_sample=sample,
                    duration_ms=(time.monotonic() - start) * 1000,
                )

            else:
                return RuleResult(
                    rule_id=rule.metadata.id,
                    passed=False,
                    error=f"Unsupported rule type: {logic.type}",
                    duration_ms=(time.monotonic() - start) * 1000,
                )

        except Exception as e:
            return RuleResult(
                rule_id=rule.metadata.id,
                passed=False,
                error=str(e),
                duration_ms=(time.monotonic() - start) * 1000,
            )

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
