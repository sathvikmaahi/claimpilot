"""Shared context and payload models for deterministic orchestration."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from core.agents.contract import AgentRequest
from core.composition.roles import AgentRole


class SubAgentStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"
    RETRY = "retry"


class SubAgentResult(BaseModel):
    """Normalized output from a single sub-agent invocation."""

    node_id: str
    role: AgentRole
    status: SubAgentStatus = SubAgentStatus.SUCCESS
    message: str = ""
    structured: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status == SubAgentStatus.SUCCESS

    @property
    def failed(self) -> bool:
        return self.status == SubAgentStatus.FAILURE


class OrchestrationContext(BaseModel):
    """Mutable execution context passed through the orchestration graph."""

    request: AgentRequest
    session_id: str
    user_message: str
    shared: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, SubAgentResult] = Field(default_factory=dict)
    trace: list[str] = Field(default_factory=list)

    def record(self, node_id: str, result: SubAgentResult) -> None:
        self.outputs[node_id] = result
        self.trace.append(node_id)

    def get_message(self, node_id: str, default: str = "") -> str:
        result = self.outputs.get(node_id)
        return result.message if result else default

    def get_structured(self, node_id: str, key: str, default: Any = None) -> Any:
        result = self.outputs.get(node_id)
        if result is None:
            return default
        return result.structured.get(key, default)

    def latest_message(self, default: str = "") -> str:
        if not self.trace:
            return default
        return self.get_message(self.trace[-1], default)

    def fork(self) -> OrchestrationContext:
        """Create an isolated copy for parallel branch execution."""
        return self.model_copy(deep=True)

    def merge_branch(self, branch: OrchestrationContext) -> None:
        """Merge outputs and trace from a parallel branch."""
        self.outputs.update(branch.outputs)
        self.shared.update(branch.shared)
        self.trace.extend(branch.trace)
