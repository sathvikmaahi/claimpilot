"""ADK Runner adapter implementing the shared agent contract."""

from __future__ import annotations

import uuid
from typing import Any, cast

import structlog
from google.adk.agents.base_agent import BaseAgent
from google.adk.runners import Runner
from google.adk.sessions.base_session_service import BaseSessionService
from google.genai import types

from core.agents.contract import AgentContract, AgentRequest, AgentResponse
from core.config import get_settings
from core.exceptions import AgentExecutionError

logger = structlog.get_logger(__name__)


def _extract_text_from_content(content: types.Content | None) -> str:
    if content is None or not content.parts:
        return ""
    chunks: list[str] = []
    for part in content.parts:
        if part.text:
            chunks.append(part.text)
    return "".join(chunks)


def _event_to_dict(event: Any) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        dumped = event.model_dump(mode="json", exclude_none=True)
        return cast(dict[str, Any], dumped)
    return {"repr": repr(event)}


class ADKAgentHandler(AgentContract):
    """Wraps a Google ADK root agent with the shared service contract."""

    def __init__(
        self,
        *,
        agent_id: str,
        name: str,
        description: str,
        root_agent: BaseAgent,
        session_service: BaseSessionService,
        app_name: str,
    ) -> None:
        self._agent_id = agent_id
        self._name = name
        self._description = description

        plugins = []
        settings = get_settings()
        if settings.otel_enabled:
            from google.adk.plugins.auto_tracing_plugin import AutoTracingPlugin
            from google.adk.plugins.base_plugin import BasePlugin

            plugins.append(AutoTracingPlugin())

        self._runner = Runner(
            agent=root_agent,
            app_name=app_name,
            session_service=session_service,
            auto_create_session=True,
            plugins=cast(list[BasePlugin] | None, plugins or None),
        )

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    async def run(self, request: AgentRequest) -> AgentResponse:
        session_id = request.session_id or str(uuid.uuid4())
        user_message = types.Content(
            role="user",
            parts=[types.Part(text=request.message)],
        )

        events: list[dict[str, Any]] = []
        final_text = ""

        try:
            async for event in self._runner.run_async(
                user_id=request.user_id,
                session_id=session_id,
                new_message=user_message,
            ):
                events.append(_event_to_dict(event))
                if event.content and event.author and event.author != "user":
                    text = _extract_text_from_content(event.content)
                    if text:
                        final_text = text
                if event.error_message:
                    raise AgentExecutionError(
                        event.error_message,
                        details={"agent_id": self._agent_id, "session_id": session_id},
                    )
        except AgentExecutionError:
            raise
        except Exception as exc:
            logger.exception(
                "agent_execution_failed",
                agent_id=self._agent_id,
                session_id=session_id,
            )
            raise AgentExecutionError(
                f"Agent '{self._agent_id}' failed: {exc}",
                details={"agent_id": self._agent_id, "session_id": session_id},
            ) from exc

        logger.info(
            "agent_run_completed",
            agent_id=self._agent_id,
            session_id=session_id,
            event_count=len(events),
        )

        return AgentResponse(
            agent_id=self._agent_id,
            session_id=session_id,
            message=final_text,
            events=events,
            metadata=request.metadata,
        )
