"""Sub-agent node implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from google.adk import Agent
from google.adk.runners import Runner
from google.adk.sessions.base_session_service import BaseSessionService
from google.genai import types

from core.composition.context import OrchestrationContext, SubAgentResult, SubAgentStatus
from core.composition.roles import AgentRole
from core.exceptions import AgentExecutionError

logger = structlog.get_logger(__name__)

SubAgentCallable = Callable[[OrchestrationContext], Awaitable[SubAgentResult]]


class SubAgent(ABC):
    """Internal agent invoked by the orchestration layer."""

    def __init__(self, *, node_id: str, role: AgentRole) -> None:
        self.node_id = node_id
        self.role = role

    @abstractmethod
    async def execute(self, context: OrchestrationContext) -> SubAgentResult:
        """Run the sub-agent against the current orchestration context."""


class FunctionSubAgent(SubAgent):
    """Deterministic sub-agent backed by a plain async callable (ideal for tests)."""

    def __init__(
        self,
        *,
        node_id: str,
        role: AgentRole,
        handler: SubAgentCallable,
    ) -> None:
        super().__init__(node_id=node_id, role=role)
        self._handler = handler

    async def execute(self, context: OrchestrationContext) -> SubAgentResult:
        return await self._handler(context)


class ADKSubAgent(SubAgent):
    """Sub-agent that delegates inference to a Google ADK Agent via Runner."""

    def __init__(
        self,
        *,
        node_id: str,
        role: AgentRole,
        agent: Agent,
        session_service: BaseSessionService,
        app_name: str,
        input_template: str = "{user_message}",
    ) -> None:
        super().__init__(node_id=node_id, role=role)
        self._input_template = input_template
        self._runner = Runner(
            agent=agent,
            app_name=app_name,
            session_service=session_service,
            auto_create_session=True,
        )

    def _build_prompt(self, context: OrchestrationContext) -> str:
        template_vars: dict[str, Any] = {
            "user_message": context.user_message,
            "session_id": context.session_id,
        }
        for node_id, result in context.outputs.items():
            template_vars[node_id] = result.message
            template_vars[f"{node_id}_structured"] = result.structured

        return self._input_template.format(**template_vars)

    async def execute(self, context: OrchestrationContext) -> SubAgentResult:
        prompt = self._build_prompt(context)
        user_message = types.Content(role="user", parts=[types.Part(text=prompt)])
        final_text = ""
        structured: dict[str, Any] = {}

        try:
            async for event in self._runner.run_async(
                user_id=context.request.user_id,
                session_id=f"{context.session_id}:{self.node_id}",
                new_message=user_message,
            ):
                if event.content and event.author and event.author != "user":
                    parts = event.content.parts or []
                    final_text = "".join(part.text or "" for part in parts)
                if event.error_message:
                    raise AgentExecutionError(event.error_message)
                if event.custom_metadata:
                    structured.update(dict(event.custom_metadata))
        except AgentExecutionError as exc:
            return SubAgentResult(
                node_id=self.node_id,
                role=self.role,
                status=SubAgentStatus.FAILURE,
                error=str(exc),
            )
        except Exception as exc:
            logger.exception("sub_agent_failed", node_id=self.node_id)
            return SubAgentResult(
                node_id=self.node_id,
                role=self.role,
                status=SubAgentStatus.FAILURE,
                error=str(exc),
            )

        return SubAgentResult(
            node_id=self.node_id,
            role=self.role,
            status=SubAgentStatus.SUCCESS,
            message=final_text,
            structured=structured,
        )
