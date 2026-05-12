"""LangGraph orchestrator — wires plan → execute → diagnose → report."""

from __future__ import annotations

import uuid

from langgraph.graph import END, StateGraph

from ..adapters.llm.anthropic import AnthropicAdapter
from ..adapters.llm.base import LLMAdapter
from ..adapters.warehouse.base import WarehouseAdapter
from ..adapters.warehouse.duckdb import DuckDBAdapter
from ..rules.schema import DataQualityRule
from .lineage.openlineage import LineageGraph
from .nodes.classify import classify_node
from .nodes.diagnose import diagnose_node
from .nodes.execute import execute_node
from .nodes.plan import plan_node
from .nodes.rca import rca_node
from .nodes.reconcile import reconcile_node
from .nodes.remediate import remediate_node
from .nodes.report import report_node
from .state import AegisState

_UNSET = object()  # sentinel — distinguishes "not provided" from explicit None


class AegisAgent:
    """Agentic data quality orchestrator built on LangGraph."""

    def __init__(
        self,
        warehouse_adapter: WarehouseAdapter | None = None,
        llm_adapter: LLMAdapter | None = _UNSET,  # type: ignore[assignment]
        lineage_graph: LineageGraph | None = None,
    ):
        self._warehouse: WarehouseAdapter = warehouse_adapter or DuckDBAdapter()
        # If caller explicitly passes llm_adapter=None → no-LLM / offline mode.
        # If caller omits the argument → default to AnthropicAdapter.
        if llm_adapter is _UNSET:
            self._llm: LLMAdapter | None = AnthropicAdapter()
        else:
            self._llm = llm_adapter  # type: ignore[assignment]
        self._lineage: LineageGraph = lineage_graph or {}
        self._graph = self._build_graph()

    def _build_graph(self):
        builder: StateGraph = StateGraph(AegisState)

        # Capture adapter references so closures are stable
        warehouse = self._warehouse
        llm = self._llm
        lineage = self._lineage

        async def _execute(state: AegisState) -> AegisState:
            return await execute_node(state, warehouse)

        async def _classify(state: AegisState) -> AegisState:
            return await classify_node(state, llm)

        async def _diagnose(state: AegisState) -> AegisState:
            return await diagnose_node(state, llm)

        async def _rca(state: AegisState) -> AegisState:
            return await rca_node(state, llm, lineage)

        async def _remediate(state: AegisState) -> AegisState:
            return await remediate_node(state, llm)

        builder.add_node("plan", plan_node)
        builder.add_node("execute", _execute)
        builder.add_node("reconcile", reconcile_node)
        builder.add_node("classify", _classify)
        builder.add_node("diagnose", _diagnose)
        builder.add_node("rca", _rca)
        builder.add_node("remediate", _remediate)
        builder.add_node("report", report_node)

        builder.set_entry_point("plan")
        builder.add_edge("plan", "execute")
        builder.add_edge("execute", "reconcile")
        builder.add_edge("reconcile", "classify")
        builder.add_edge("classify", "diagnose")
        builder.add_edge("diagnose", "rca")
        builder.add_edge("rca", "remediate")
        builder.add_edge("remediate", "report")
        builder.add_edge("report", END)

        return builder.compile()

    async def run(
        self,
        rules: list[DataQualityRule],
        triggered_by: str = "cli",
        run_id: str | None = None,
    ) -> AegisState:
        """Run validation for the given rules and return the final state."""
        initial: AegisState = {
            "run_id": run_id or str(uuid.uuid4()),
            "triggered_by": triggered_by,
            "scope": {
                "tables": list({r.spec_scope.table for r in rules}),
                "rule_ids": None,
            },
            "rules": rules,
            "plan": [],
            "rule_results": [],
            "failures": [],
            "classified_failures": {},
            "reconciliation_summary": {},
            "diagnoses": [],
            "rca_results": [],
            "remediation_proposals": [],
            "report": {},
            "trajectory": [],
            "cost_total_usd": 0.0,
            "tokens_total": 0,
            "error": None,
        }
        return await self._graph.ainvoke(initial)
