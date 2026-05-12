"""Trajectory export — converts run decisions to portable formats."""

from __future__ import annotations

from pathlib import Path

from ..memory.store import DB_PATH
from .logger import get_decisions


async def export_json(run_id: str, db_path: Path = DB_PATH) -> list[dict]:
    """Return raw decisions list for a run as JSON-serialisable dicts."""
    return await get_decisions(run_id, db_path)


async def export_sharegpt(run_id: str, db_path: Path = DB_PATH) -> dict:
    """
    Export decisions as a ShareGPT conversation for RL / fine-tuning datasets.

    Each LLM decision becomes one (human, gpt) turn pair:
      human  = the input_summary (what was sent to the LLM)
      gpt    = the output_summary (what the LLM returned)

    Non-LLM steps (no model field) are emitted as system notes.
    """
    decisions = await get_decisions(run_id, db_path)
    conversations: list[dict] = []

    for d in decisions:
        if d.get("model"):
            conversations.append({"from": "human", "value": d["input_summary"]})
            conversations.append({"from": "gpt", "value": d["output_summary"]})
        else:
            conversations.append({"from": "system", "value": f"[{d['step']}] {d['input_summary']}"})

    return {
        "id": run_id,
        "conversations": conversations,
        "metadata": {
            "source": "aegis-dq",
            "total_decisions": len(decisions),
            "llm_decisions": sum(1 for d in decisions if d.get("model")),
        },
    }
