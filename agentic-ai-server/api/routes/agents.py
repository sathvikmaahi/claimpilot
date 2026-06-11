"""Registry-driven REST endpoints for registered agents."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.agents.contract import AgentRequest, AgentResponse
from core.agents.registry import AgentRegistry
from core.dependencies import get_agent_registry
from core.exceptions import AgentExecutionError, AgenticAIError, AgentNotFoundError

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentInfo(BaseModel):
    id: str
    name: str
    description: str


class AgentListResponse(BaseModel):
    agents: list[AgentInfo]


class RunAgentRequest(BaseModel):
    message: str = Field(..., min_length=1)
    user_id: str = "anonymous"
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _handle_agent_errors(exc: AgenticAIError) -> HTTPException:
    if isinstance(exc, AgentNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if isinstance(exc, AgentExecutionError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": exc.message, "details": exc.details},
        )
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.message)


@router.get("", response_model=AgentListResponse)
async def list_agents(
    registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentListResponse:
    agents = [
        AgentInfo(id=agent.agent_id, name=agent.name, description=agent.description)
        for agent in registry.list_agents()
    ]
    return AgentListResponse(agents=agents)


@router.get("/{agent_id}", response_model=AgentInfo)
async def get_agent(
    agent_id: str,
    registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentInfo:
    try:
        agent = registry.get(agent_id)
    except AgentNotFoundError as exc:
        raise _handle_agent_errors(exc) from exc
    return AgentInfo(id=agent.agent_id, name=agent.name, description=agent.description)


@router.post("/{agent_id}/run", response_model=AgentResponse)
async def run_agent(
    agent_id: str,
    body: RunAgentRequest,
    registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentResponse:
    try:
        agent = registry.get(agent_id)
        request = AgentRequest(
            message=body.message,
            user_id=body.user_id,
            session_id=body.session_id,
            metadata=body.metadata,
        )
        return await agent.run(request)
    except AgenticAIError as exc:
        logger.warning("agent_request_failed", agent_id=agent_id, error=exc.message)
        raise _handle_agent_errors(exc) from exc


@router.get("/{agent_id}/health")
async def agent_health(
    agent_id: str,
    registry: AgentRegistry = Depends(get_agent_registry),
) -> dict[str, object]:
    try:
        agent = registry.get(agent_id)
        healthy = await agent.health()
    except AgentNotFoundError as exc:
        raise _handle_agent_errors(exc) from exc

    return {"agent_id": agent_id, "healthy": healthy}
