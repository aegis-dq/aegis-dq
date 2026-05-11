"""DuckDB warehouse adapter."""

from __future__ import annotations

import concurrent.futures
import threading
import time

import duckdb

from ...rules.schema import DataQualityRule, RuleResult, RuleType
from .base import WarehouseAdapter

# Single-threaded executor — DuckDB connections are not thread-safe, so we
# serialise all sync work onto one dedicated thread that owns the connection.
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="duckdb")


class DuckDBAdapter(WarehouseAdapter):
    """Warehouse adapter backed by DuckDB (in-memory or file-based)."""

    def __init__(self, path: str = ":memory:"):
        self._path = path
        self._lock = threading.Lock()
        self._conn: duckdb.DuckDBPyConnection | None = None

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        with self._lock:
            if self._conn is None:
                self._conn = duckdb.connect(self._path)
        return self._conn

    async def execute_rule(self, rule: DataQualityRule) -> RuleResult:
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_EXECUTOR, self._execute_sync, rule)

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
