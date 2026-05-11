"""Integration tests for the DuckDB warehouse adapter."""

from __future__ import annotations

import pytest

from aegis.adapters.warehouse.duckdb import DuckDBAdapter
from aegis.rules.schema import (
    DataQualityRule,
    RuleLogic,
    RuleMetadata,
    RuleScope,
    RuleType,
    Severity,
)


@pytest.fixture
def adapter_with_data():
    adapter = DuckDBAdapter(":memory:")
    conn = adapter._get_conn()
    conn.execute("CREATE TABLE orders (order_id INT, revenue FLOAT)")
    conn.execute(
        "INSERT INTO orders VALUES (1, 100.0), (2, -50.0), (3, NULL), (NULL, 200.0)"
    )
    return adapter


def make_rule(rule_type: RuleType, **kwargs) -> DataQualityRule:
    columns = kwargs.pop("columns", ["order_id"])
    return DataQualityRule(
        apiVersion="aegis.dev/v1",
        metadata=RuleMetadata(id=f"test_{rule_type.value}", severity=Severity.HIGH),
        scope=RuleScope(table="orders", columns=columns),
        logic=RuleLogic(type=rule_type, **kwargs),
    )


@pytest.mark.asyncio
async def test_not_null_fails(adapter_with_data):
    rule = make_rule(RuleType.NOT_NULL, columns=["order_id"])
    result = await adapter_with_data.execute_rule(rule)
    assert not result.passed
    assert result.row_count_failed == 1
    assert result.row_count_checked == 4


@pytest.mark.asyncio
async def test_not_null_passes(adapter_with_data):
    # revenue column: row with revenue=NULL is row 3, but order_id NULL row has revenue 200
    # The table has one revenue NULL (row 3) — test with revenue
    rule = make_rule(RuleType.NOT_NULL, columns=["revenue"])
    result = await adapter_with_data.execute_rule(rule)
    assert not result.passed  # row 3 has NULL revenue
    assert result.row_count_failed == 1


@pytest.mark.asyncio
async def test_sql_expression_fails(adapter_with_data):
    rule = make_rule(RuleType.SQL_EXPRESSION, expression="revenue >= 0", columns=[])
    result = await adapter_with_data.execute_rule(rule)
    assert not result.passed
    assert result.row_count_failed >= 1  # row 2 has revenue = -50


@pytest.mark.asyncio
async def test_sql_expression_passes(adapter_with_data):
    rule = make_rule(RuleType.SQL_EXPRESSION, expression="order_id IS NOT NULL OR revenue IS NOT NULL", columns=[])
    result = await adapter_with_data.execute_rule(rule)
    # All rows satisfy this — order_id IS NOT NULL OR revenue IS NOT NULL
    # row 4: order_id=NULL, revenue=200 -> passes (revenue not null)
    # row 3: order_id=3, revenue=NULL -> passes (order_id not null)
    assert result.passed


@pytest.mark.asyncio
async def test_unique_fails(adapter_with_data):
    # Insert a duplicate to ensure uniqueness fails
    adapter_with_data._get_conn().execute("INSERT INTO orders VALUES (1, 999.0)")
    rule = make_rule(RuleType.UNIQUE, columns=["order_id"])
    result = await adapter_with_data.execute_rule(rule)
    assert not result.passed
    assert result.row_count_failed >= 1


@pytest.mark.asyncio
async def test_row_count_passes(adapter_with_data):
    rule = make_rule(RuleType.ROW_COUNT, threshold=1, columns=[])
    result = await adapter_with_data.execute_rule(rule)
    assert result.passed
    assert result.row_count_checked == 4


@pytest.mark.asyncio
async def test_row_count_fails(adapter_with_data):
    rule = make_rule(RuleType.ROW_COUNT, threshold=1000, columns=[])
    result = await adapter_with_data.execute_rule(rule)
    assert not result.passed


@pytest.mark.asyncio
async def test_custom_sql_passes(adapter_with_data):
    rule = make_rule(
        RuleType.CUSTOM_SQL,
        query="SELECT COUNT(*) > 0 AS passed, COUNT(*) AS row_count FROM orders",
        columns=[],
    )
    result = await adapter_with_data.execute_rule(rule)
    assert result.passed


@pytest.mark.asyncio
async def test_custom_sql_fails(adapter_with_data):
    rule = make_rule(
        RuleType.CUSTOM_SQL,
        query="SELECT COUNT(*) > 1000 AS passed, COUNT(*) AS row_count FROM orders",
        columns=[],
    )
    result = await adapter_with_data.execute_rule(rule)
    assert not result.passed


@pytest.mark.asyncio
async def test_failure_sample_populated(adapter_with_data):
    rule = make_rule(RuleType.NOT_NULL, columns=["order_id"])
    result = await adapter_with_data.execute_rule(rule)
    assert not result.passed
    assert len(result.failure_sample) >= 1


@pytest.mark.asyncio
async def test_duration_ms_populated(adapter_with_data):
    rule = make_rule(RuleType.NOT_NULL, columns=["order_id"])
    result = await adapter_with_data.execute_rule(rule)
    assert result.duration_ms >= 0.0


@pytest.mark.asyncio
async def test_unique_missing_columns_returns_error():
    adapter = DuckDBAdapter(":memory:")
    adapter._get_conn().execute("CREATE TABLE t (a INT)")
    adapter._get_conn().execute("INSERT INTO t VALUES (1)")
    rule = DataQualityRule(
        apiVersion="aegis.dev/v1",
        metadata=RuleMetadata(id="unique_no_col", severity=Severity.HIGH),
        scope=RuleScope(table="t", columns=[]),
        logic=RuleLogic(type=RuleType.UNIQUE),
    )
    result = await adapter.execute_rule(rule)
    assert not result.passed
    assert result.error is not None
    assert "columns" in result.error.lower()


@pytest.mark.asyncio
async def test_adapter_close():
    adapter = DuckDBAdapter(":memory:")
    adapter._get_conn()  # open connection
    await adapter.close()
    assert adapter._conn is None
