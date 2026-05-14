"""AegisProject — loads aegis.yaml and provides project-level defaults.

Walks up from any path to find the nearest aegis.yaml, the same way
git finds .git. This means `aegis pipeline run pipelines/fraud/pipeline.yaml`
automatically picks up the root aegis.yaml without any flags.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

PROJECT_FILE = "aegis.yaml"


class LLMDefaults(BaseModel):
    provider: str = "anthropic"
    model: str | None = None


class WarehouseDefaults(BaseModel):
    type: str = "duckdb"
    connection: dict[str, Any] = Field(default_factory=dict)


class AuditConfig(BaseModel):
    db_path: str = ".aegis/history.db"


class AegisProject(BaseModel):
    """Parsed aegis.yaml — project-wide defaults inherited by all pipelines."""

    default_llm: LLMDefaults = Field(default_factory=LLMDefaults)
    default_warehouse: WarehouseDefaults = Field(default_factory=WarehouseDefaults)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    pipelines_dir: str = "pipelines"

    # The directory that contains aegis.yaml — set on load, not in YAML
    root: Path = Field(default=Path("."), exclude=True)

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def find(cls, start: Path) -> AegisProject | None:
        """Walk up from *start* looking for aegis.yaml. Returns None if not found."""
        current = start.resolve() if not start.is_dir() else start.resolve()
        if not current.is_dir():
            current = current.parent
        for directory in [current, *current.parents]:
            candidate = directory / PROJECT_FILE
            if candidate.exists():
                return cls.load(candidate)
        return None

    @classmethod
    def load(cls, path: Path) -> AegisProject:
        """Load aegis.yaml from an explicit path."""
        raw = yaml.safe_load(path.read_text()) or {}
        project = cls.model_validate(raw)
        object.__setattr__(project, "root", path.parent.resolve())
        return project

    def resolve_db_path(self) -> Path:
        """Return audit db_path resolved relative to the project root."""
        p = Path(self.audit.db_path)
        return p if p.is_absolute() else self.root / p

    def resolve_pipelines_dir(self) -> Path:
        p = Path(self.pipelines_dir)
        return p if p.is_absolute() else self.root / p
