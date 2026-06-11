"""Automatic agent execution instrumentation wrapper."""

from __future__ import annotations

from typing import Any

import structlog

from core.agents.contract import AgentContract, AgentRequest, AgentResponse
from core.exceptions import AgentExecutionError, AgenticAIError
from telemetry.recorder import ExecutionTimer, TelemetryRecorder

logger = structlog.get_logger(__name__)


class InstrumentedAgentHandler(AgentContract):
    """Wraps any agent to emit traces and persist execution telemetry automatically."""

    def __init__(self, delegate: AgentContract, recorder: TelemetryRecorder) -> None:
        self._delegate = delegate
        self._recorder = recorder

    @property
    def agent_id(self) -> str:
        return self._delegate.agent_id

    @property
    def name(self) -> str:
        return self._delegate.name

    @property
    def description(self) -> str:
        return self._delegate.description

    @property
    def interaction_mode(self) -> str:
        return getattr(self._delegate, "interaction_mode", "stateless")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    async def run(self, request: AgentRequest) -> AgentResponse:
        timer = ExecutionTimer()
        request_id = (request.metadata or {}).get("request_id")
        status = "success"
        error_message: str | None = None
        response: AgentResponse | None = None

        with self._recorder.agent_execution_span(
            self.agent_id,
            request.session_id,
            request.user_id,
        ):
            try:
                response = await self._delegate.run(request)
                return response
            except AgenticAIError as exc:
                status = "failure"
                error_message = exc.message
                raise
            except Exception as exc:
                status = "failure"
                error_message = str(exc)
                raise AgentExecutionError(str(exc)) from exc
            finally:
                await self._recorder.record_execution(
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    session_id=request.session_id,
                    user_id=request.user_id,
                    status=status,
                    latency_ms=timer.elapsed_ms,
                    request_id=str(request_id) if request_id else None,
                    events=response.events if response else None,
                    error_message=error_message,
                    metadata={
                        "interaction_mode": getattr(self._delegate, "interaction_mode", "stateless")
                    },
                )

    async def health(self) -> bool:
        return await self._delegate.health()
