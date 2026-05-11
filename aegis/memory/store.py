"""SQLite-backed run history store using aiosqlite."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

DB_PATH = Path.home() / ".aegis" / "history.db"


async def init_db(path: Path = DB_PATH) -> None:
    """Create the history database and runs table if they don't exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id       TEXT PRIMARY KEY,
                timestamp    TEXT NOT NULL,
                triggered_by TEXT,
                total_rules  INTEGER,
                passed       INTEGER,
                failed       INTEGER,
                cost_usd     REAL,
                report_json  TEXT
            )
            """
        )
        await db.commit()


async def save_run(report: dict, path: Path = DB_PATH) -> None:
    """Persist a completed run report to the history database."""
    await init_db(path)
    s = report.get("summary", {})
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?)",
            (
                report["run_id"],
                report.get("timestamp", datetime.now(UTC).isoformat()),
                report.get("triggered_by", "unknown"),
                s.get("total_rules", 0),
                s.get("passed", 0),
                s.get("failed", 0),
                report.get("cost_usd", 0.0),
                json.dumps(report),
            ),
        )
        await db.commit()
