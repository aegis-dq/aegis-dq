"""Tests for the Airflow operator (fully mocked — no Airflow installation required)."""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Install minimal Airflow stubs before importing the operator so the real
# apache-airflow package is never required.
# ---------------------------------------------------------------------------

def _install_airflow_mock() -> None:
    """Inject lightweight airflow stubs into sys.modules."""

    class FakeBaseOperator:
        template_fields: tuple[str, ...] = ()

        def __init__(self, **kwargs):
            # Absorb task_id and other standard BaseOperator kwargs
            self.task_id = kwargs.get("task_id", "test_task")

        @property
        def log(self):
            import logging
            return logging.getLogger("aegis.test")

    class FakeAirflowException(Exception):
        pass

    airflow_mod = types.ModuleType("airflow")
    models_mod = types.ModuleType("airflow.models")
    baseop_mod = types.ModuleType("airflow.models.baseoperator")
    exc_mod = types.ModuleType("airflow.exceptions")

    baseop_mod.BaseOperator = FakeBaseOperator
    exc_mod.AirflowException = FakeAirflowException
    airflow_mod.models = models_mod
    models_mod.baseoperator = baseop_mod

    sys.modules.setdefault("airflow", airflow_mod)
    sys.modules.setdefault("airflow.models", models_mod)
    sys.modules.setdefault("airflow.models.baseoperator", baseop_mod)
    sys.modules.setdefault("airflow.exceptions", exc_mod)


_install_airflow_mock()

from aegis.integrations.airflow.operator import AegisOperator  # noqa: E402

# Grab the stubbed AirflowException for assertions
_AirflowException = sys.modules["airflow.exceptions"].AirflowException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(failed: int = 0, passed: int = 1) -> dict:
    """Return a minimal AegisState-shaped dict."""
    return {
        "run_id": "test-run-001",
        "report": {
            "summary": {
                "total": passed + failed,
                "passed": passed,
                "failed": failed,
            }
        },
    }


def _make_context(run_id: str = "airflow-run-xyz") -> dict:
    """Return a minimal Airflow task-instance context."""
    ti = MagicMock()
    return {"run_id": run_id, "ti": ti}


def _patch_agent(state: dict):
    """Return a context manager that patches AegisAgent.run with an AsyncMock."""
    return patch(
        "aegis.integrations.airflow.operator.AegisAgent",
        autospec=False,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAegisOperator:

    def _make_operator(self, **kwargs) -> AegisOperator:
        defaults = dict(
            task_id="dq_check",
            rules_path="/tmp/rules.yaml",
            llm_provider="none",
        )
        defaults.update(kwargs)
        return AegisOperator(**defaults)

    # ------------------------------------------------------------------
    # template_fields
    # ------------------------------------------------------------------

    def test_template_fields(self):
        op = self._make_operator()
        assert "rules_path" in op.template_fields
        assert "db_path" in op.template_fields
        assert "run_id" in op.template_fields

    # ------------------------------------------------------------------
    # Happy path — xcom push
    # ------------------------------------------------------------------

    def test_operator_runs_and_pushes_xcom(self):
        state = _make_state(failed=0, passed=3)
        context = _make_context()

        with patch("aegis.integrations.airflow.operator.AegisAgent") as MockAgent, \
             patch("aegis.integrations.airflow.operator.load_rules", return_value=[]), \
             patch("aegis.integrations.airflow.operator.DuckDBAdapter"):

            instance = MockAgent.return_value
            instance.run = AsyncMock(return_value=state)

            op = self._make_operator(fail_on_failure=True, xcom_key="my_report")
            result = op.execute(context)

        context["ti"].xcom_push.assert_called_once_with(
            key="my_report", value=state["report"]
        )
        assert result == state["report"]

    # ------------------------------------------------------------------
    # fail_on_failure=True raises when failures > 0
    # ------------------------------------------------------------------

    def test_fail_on_failure_raises(self):
        state = _make_state(failed=2, passed=1)
        context = _make_context()

        with patch("aegis.integrations.airflow.operator.AegisAgent") as MockAgent, \
             patch("aegis.integrations.airflow.operator.load_rules", return_value=[]), \
             patch("aegis.integrations.airflow.operator.DuckDBAdapter"):

            instance = MockAgent.return_value
            instance.run = AsyncMock(return_value=state)

            op = self._make_operator(fail_on_failure=True)
            with pytest.raises(_AirflowException, match="2 failed rule"):
                op.execute(context)

    # ------------------------------------------------------------------
    # fail_on_failure=False — no exception even with failures
    # ------------------------------------------------------------------

    def test_no_fail_when_fail_on_failure_false(self):
        state = _make_state(failed=2, passed=1)
        context = _make_context()

        with patch("aegis.integrations.airflow.operator.AegisAgent") as MockAgent, \
             patch("aegis.integrations.airflow.operator.load_rules", return_value=[]), \
             patch("aegis.integrations.airflow.operator.DuckDBAdapter"):

            instance = MockAgent.return_value
            instance.run = AsyncMock(return_value=state)

            op = self._make_operator(fail_on_failure=False)
            result = op.execute(context)  # must NOT raise

        assert result["summary"]["failed"] == 2

    # ------------------------------------------------------------------
    # Custom run_id is forwarded to agent.run
    # ------------------------------------------------------------------

    def test_custom_run_id_used(self):
        state = _make_state()
        context = _make_context(run_id="ctx-run-id")

        with patch("aegis.integrations.airflow.operator.AegisAgent") as MockAgent, \
             patch("aegis.integrations.airflow.operator.load_rules", return_value=[]), \
             patch("aegis.integrations.airflow.operator.DuckDBAdapter"):

            instance = MockAgent.return_value
            instance.run = AsyncMock(return_value=state)

            op = self._make_operator(run_id="custom-run-42")
            op.execute(context)

            instance.run.assert_awaited_once()
            _, kwargs = instance.run.call_args
            assert kwargs.get("run_id") == "custom-run-42"

    # ------------------------------------------------------------------
    # run_id=None falls back to context["run_id"]
    # ------------------------------------------------------------------

    def test_run_id_falls_back_to_context(self):
        state = _make_state()
        context = _make_context(run_id="from-airflow-context")

        with patch("aegis.integrations.airflow.operator.AegisAgent") as MockAgent, \
             patch("aegis.integrations.airflow.operator.load_rules", return_value=[]), \
             patch("aegis.integrations.airflow.operator.DuckDBAdapter"):

            instance = MockAgent.return_value
            instance.run = AsyncMock(return_value=state)

            op = self._make_operator(run_id=None)
            op.execute(context)

            instance.run.assert_awaited_once()
            _, kwargs = instance.run.call_args
            assert kwargs.get("run_id") == "from-airflow-context"

    # ------------------------------------------------------------------
    # llm_provider="none" passes llm_adapter=None to AegisAgent
    # ------------------------------------------------------------------

    def test_llm_none_provider(self):
        state = _make_state()
        context = _make_context()

        with patch("aegis.integrations.airflow.operator.AegisAgent") as MockAgent, \
             patch("aegis.integrations.airflow.operator.load_rules", return_value=[]), \
             patch("aegis.integrations.airflow.operator.DuckDBAdapter"):

            instance = MockAgent.return_value
            instance.run = AsyncMock(return_value=state)

            op = self._make_operator(llm_provider="none")
            op.execute(context)

            MockAgent.assert_called_once()
            _, kwargs = MockAgent.call_args
            assert kwargs.get("llm_adapter") is None
