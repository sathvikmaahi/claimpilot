"""Deterministic handlers demonstrating the chat-oriented agent system pattern."""

from __future__ import annotations

from typing import Any

from google.adk.sessions.base_session_service import BaseSessionService

from core.composition.context import OrchestrationContext, SubAgentResult, SubAgentStatus
from core.composition.factory import create_agent_system_handler
from core.composition.handler import AgentSystemHandler
from core.composition.nodes import FunctionSubAgent
from core.composition.roles import AgentRole
from core.config import Settings

_TASK_KEYWORDS = ("submit", "process", "claim", "file", "create")


async def _orchestrator_handler(context: OrchestrationContext) -> SubAgentResult:
    lowered = context.user_message.lower()
    route = "task" if any(keyword in lowered for keyword in _TASK_KEYWORDS) else "chat"
    return SubAgentResult(
        node_id="orchestrator",
        role=AgentRole.ORCHESTRATOR,
        status=SubAgentStatus.SUCCESS,
        message=f"Classified intent as '{route}'.",
        structured={"route": route},
    )


async def _conversational_handler(context: OrchestrationContext) -> SubAgentResult:
    return SubAgentResult(
        node_id="conversational",
        role=AgentRole.CONVERSATIONAL,
        status=SubAgentStatus.SUCCESS,
        message=f"Happy to chat! You said: {context.user_message}",
    )


async def _task_handler(context: OrchestrationContext) -> SubAgentResult:
    return SubAgentResult(
        node_id="task_worker",
        role=AgentRole.TASK,
        status=SubAgentStatus.SUCCESS,
        message=f"Task accepted and queued: {context.user_message}",
        structured={"task_status": "queued"},
    )


async def _memory_handler(context: OrchestrationContext) -> SubAgentResult:
    specialist = context.get_message("conversational") or context.get_message("task_worker")
    preview = context.user_message[:40]
    summary = f"Session summary — user asked about '{preview}'; specialist replied."
    return SubAgentResult(
        node_id="session_memory",
        role=AgentRole.MEMORY,
        status=SubAgentStatus.SUCCESS,
        message=summary,
        structured={"summary": summary, "specialist_preview": specialist[:80]},
    )


def _demo_node_overrides() -> dict[str, FunctionSubAgent]:
    return {
        "orchestrator": FunctionSubAgent(
            node_id="orchestrator",
            role=AgentRole.ORCHESTRATOR,
            handler=_orchestrator_handler,
        ),
        "conversational": FunctionSubAgent(
            node_id="conversational",
            role=AgentRole.CONVERSATIONAL,
            handler=_conversational_handler,
        ),
        "task_worker": FunctionSubAgent(
            node_id="task_worker",
            role=AgentRole.TASK,
            handler=_task_handler,
        ),
        "session_memory": FunctionSubAgent(
            node_id="session_memory",
            role=AgentRole.MEMORY,
            handler=_memory_handler,
        ),
    }


def create_agent_handler(
    *,
    agent_id: str,
    settings: Settings,
    session_service: BaseSessionService,
    config: dict[str, Any],
) -> AgentSystemHandler:
    """Register the chat assistant as a declarative multi-agent system."""
    return create_agent_system_handler(
        agent_id=agent_id,
        settings=settings,
        session_service=session_service,
        config=config,
        node_overrides=_demo_node_overrides(),
    )
