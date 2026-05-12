"""Airflow operator that runs Aegis DQ validation as a task."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from airflow.exceptions import AirflowException
from airflow.models.baseoperator import BaseOperator

from aegis.adapters.warehouse.duckdb import DuckDBAdapter
from aegis.core.agent import AegisAgent
from aegis.rules.parser import load_rules


class AegisOperator(BaseOperator):
    """Airflow operator that runs Aegis DQ validation as a task.

    Parameters
    ----------
    rules_path:
        Path to the YAML rules file. Supports Jinja templating.
    db_path:
        DuckDB database path or ``:memory:`` for an ephemeral in-memory DB.
        Supports Jinja templating.
    llm_provider:
        Which LLM backend to use: ``anthropic``, ``openai``, ``ollama``, or
        ``none`` to disable LLM-assisted diagnosis.
    llm_model:
        Optional model override passed to the selected LLM adapter.
    ollama_host:
        Base URL for a locally running Ollama instance.
    fail_on_failure:
        When ``True`` (default), raise :class:`AirflowException` if the DQ
        report contains any failed rules.
    xcom_key:
        XCom key under which the serialised report dict is pushed.
    run_id:
        Explicit run identifier.  Defaults to Airflow's ``context["run_id"]``
        when not provided.  Supports Jinja templating.
    """

    template_fields = ("rules_path", "db_path", "run_id")

    def __init__(
        self,
        *,
        rules_path: str,
        db_path: str = ":memory:",
        llm_provider: str = "anthropic",
        llm_model: str | None = None,
        ollama_host: str = "http://localhost:11434",
        fail_on_failure: bool = True,
        xcom_key: str = "aegis_report",
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.rules_path = rules_path
        self.db_path = db_path
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.ollama_host = ollama_host
        self.fail_on_failure = fail_on_failure
        self.xcom_key = xcom_key
        self.run_id = run_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_llm_adapter(self):
        """Construct the LLM adapter based on *llm_provider*."""
        provider = self.llm_provider.lower()

        if provider == "none":
            return None

        if provider == "anthropic":
            from aegis.adapters.llm.anthropic import AnthropicAdapter

            kwargs: dict[str, Any] = {}
            if self.llm_model:
                kwargs["model"] = self.llm_model
            return AnthropicAdapter(**kwargs)

        if provider == "openai":
            from aegis.adapters.llm.openai import OpenAIAdapter

            kwargs = {}
            if self.llm_model:
                kwargs["model"] = self.llm_model
            return OpenAIAdapter(**kwargs)

        if provider == "ollama":
            from aegis.adapters.llm.ollama import OllamaAdapter

            kwargs = {"base_url": self.ollama_host}
            if self.llm_model:
                kwargs["model"] = self.llm_model
            return OllamaAdapter(**kwargs)

        raise AirflowException(
            f"Unknown llm_provider {self.llm_provider!r}. "
            "Choose one of: anthropic, openai, ollama, none."
        )

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        # Resolve run_id — fall back to Airflow's context value
        effective_run_id: str = self.run_id or context.get("run_id") or ""

        self.log.info(
            "AegisOperator starting — rules=%s db=%s llm=%s run_id=%s",
            self.rules_path,
            self.db_path,
            self.llm_provider,
            effective_run_id,
        )

        # Build adapters
        llm_adapter = self._build_llm_adapter()
        warehouse_adapter = DuckDBAdapter(path=self.db_path)

        # Load rules
        rules = load_rules(Path(self.rules_path))
        self.log.info("Loaded %d rule(s) from %s", len(rules), self.rules_path)

        # Build and run agent
        agent = AegisAgent(
            warehouse_adapter=warehouse_adapter,
            llm_adapter=llm_adapter,
        )
        state = asyncio.run(
            agent.run(rules, triggered_by="airflow", run_id=effective_run_id or None)
        )

        report: dict[str, Any] = state.get("report", {})

        # Push report to XCom
        context["ti"].xcom_push(key=self.xcom_key, value=report)
        self.log.info("Pushed report to XCom key %r", self.xcom_key)

        # Optionally fail the task when DQ failures were found
        if self.fail_on_failure:
            failed_count: int = report.get("summary", {}).get("failed", 0)
            if failed_count > 0:
                raise AirflowException(
                    f"Aegis DQ validation found {failed_count} failed rule(s). "
                    f"See XCom key {self.xcom_key!r} for the full report."
                )

        return report
