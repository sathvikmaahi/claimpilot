"""Reusable fixtures for composition framework tests."""

from __future__ import annotations

from core.agents.contract import AgentRequest
from core.composition.context import OrchestrationContext, SubAgentResult, SubAgentStatus
from core.composition.roles import AgentRole


def make_context(message: str = "hello") -> OrchestrationContext:
    return OrchestrationContext(
        request=AgentRequest(message=message),
        session_id="test-session",
        user_message=message,
    )


def result(
    node_id: str,
    *,
    role: AgentRole = AgentRole.TASK,
    message: str = "ok",
    structured: dict | None = None,
    status: SubAgentStatus = SubAgentStatus.SUCCESS,
) -> SubAgentResult:
    return SubAgentResult(
        node_id=node_id,
        role=role,
        status=status,
        message=message,
        structured=structured or {},
    )
