"""Agent-system handler implementing the public AgentContract."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from core.agents.contract import AgentContract, AgentRequest, AgentResponse
from core.composition.context import OrchestrationContext
from core.composition.manifest import AgentSystemManifest
from core.composition.primitives import OrchestrationStep
from telemetry.tracing import get_tracer

logger = structlog.get_logger(__name__)


class AgentSystemHandler(AgentContract):
    """Public-facing handler for a multi-agent composition graph."""

    def __init__(
        self,
        *,
        manifest: AgentSystemManifest,
        pipeline: OrchestrationStep,
    ) -> None:
        self._manifest = manifest
        self._pipeline = pipeline

    @property
    def agent_id(self) -> str:
        return self._manifest.id

    @property
    def name(self) -> str:
        return self._manifest.name

    @property
    def description(self) -> str:
        return self._manifest.description

    @property
    def manifest(self) -> AgentSystemManifest:
        return self._manifest

    def _build_response_metadata(self, context: OrchestrationContext) -> dict[str, Any]:
        return {
            "system_id": self._manifest.id,
            "trace": context.trace,
            "route": context.shared.get("route"),
            "node_outputs": {
                node_id: {
                    "role": result.role,
                    "status": result.status,
                    "structured": result.structured,
                }
                for node_id, result in context.outputs.items()
            },
        }

    async def run(self, request: AgentRequest) -> AgentResponse:
        session_id = request.session_id or str(uuid.uuid4())
        context = OrchestrationContext(
            request=request,
            session_id=session_id,
            user_message=request.message,
            shared=dict(request.metadata),
        )

        tracer = get_tracer(__name__)
        with tracer.start_as_current_span(
            "agent_system.run",
            attributes={"agent_system.id": self._manifest.id, "session_id": session_id},
        ):
            result_context = await self._pipeline.run(context)
            message = result_context.latest_message(request.message)

            logger.info(
                "agent_system_completed",
                system_id=self._manifest.id,
                session_id=session_id,
                trace=result_context.trace,
            )

            return AgentResponse(
                agent_id=self._manifest.id,
                session_id=session_id,
                message=message,
                events=[
                    {
                        "node_id": node_id,
                        "role": result.role,
                        "status": result.status,
                        "message": result.message,
                        "structured": result.structured,
                        "error": result.error,
                    }
                    for node_id, result in result_context.outputs.items()
                ],
                metadata=self._build_response_metadata(result_context),
            )

    async def health(self) -> bool:
        return bool(self._manifest.nodes)
