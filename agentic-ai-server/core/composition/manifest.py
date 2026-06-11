"""Declarative manifest schema for agent systems."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from core.composition.roles import AgentRole
from core.exceptions import AgentConfigurationError


class ModelSettings(BaseModel):
    default: str = "gemini-2.0-flash"
    temperature: float | None = None
    max_output_tokens: int | None = None


class SafetySettings(BaseModel):
    max_turns: int = 20
    blocked_topics: list[str] = Field(default_factory=list)


class DependencySettings(BaseModel):
    tools: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)


class NodeManifest(BaseModel):
    role: AgentRole
    model: str | None = None
    instruction: str = ""
    input_template: str = "{user_message}"
    output_key: str | None = None
    tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


GraphStepType = Literal[
    "sequential",
    "parallel",
    "router",
    "retry",
    "node",
]


class GraphStepManifest(BaseModel):
    type: GraphStepType
    steps: list[str | GraphStepManifest] = Field(default_factory=list)
    node: str | None = None
    source: str | None = None
    field: str = "route"
    routes: dict[str, str] = Field(default_factory=dict)
    default: str | None = None
    max_attempts: int = 3
    inner: GraphStepManifest | None = None


class AgentSystemManifest(BaseModel):
    """Declarative definition of a deployable multi-agent system."""

    id: str
    name: str
    description: str = ""
    model: ModelSettings = Field(default_factory=ModelSettings)
    safety: SafetySettings = Field(default_factory=SafetySettings)
    dependencies: DependencySettings = Field(default_factory=DependencySettings)
    nodes: dict[str, NodeManifest]
    graph: list[GraphStepManifest]

    @classmethod
    def from_yaml(cls, path: Path) -> AgentSystemManifest:
        if not path.exists():
            raise AgentConfigurationError(
                f"Agent system manifest not found: {path}",
                details={"path": str(path)},
            )
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return cls.model_validate(data)

    def node_ids(self) -> list[str]:
        return sorted(self.nodes.keys())
