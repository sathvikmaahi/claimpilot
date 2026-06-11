"""Session-aware REST endpoints for conversational agents."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.agents.contract import AgentRequest, AgentResponse
from core.agents.registry import AgentRegistry
from core.conversation.models import SessionStateResponse
from core.conversation.session_manager import SessionManager
from core.conversation.wrapper import SessionAwareAgentWrapper
from core.dependencies import get_agent_registry, get_session_manager
from core.exceptions import (
    AgenticAIError,
    AgentNotFoundError,
    SessionClosedError,
    SessionNotFoundError,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    user_id: str = "anonymous"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContinueSessionRequest(BaseModel):
    message: str = Field(..., min_length=1)
    user_id: str = "anonymous"
    include_transcript: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


def _require_conversational_agent(
    agent_id: str,
    registry: AgentRegistry,
) -> SessionAwareAgentWrapper:
    try:
        agent = registry.get(agent_id)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc

    if getattr(agent, "interaction_mode", "stateless") != "conversational":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent '{agent_id}' is stateless; use POST /agents/{agent_id}/run instead",
        )

    # Unwrap InstrumentedAgentHandler if present
    inner = getattr(agent, "_delegate", agent)
    if not isinstance(inner, SessionAwareAgentWrapper):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent '{agent_id}' is not session-enabled",
        )
    return inner


def _handle_session_errors(exc: AgenticAIError) -> HTTPException:
    if isinstance(exc, SessionNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if isinstance(exc, SessionClosedError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.message)


@router.post("/{agent_id}/sessions", response_model=SessionStateResponse)
async def create_session(
    agent_id: str,
    body: CreateSessionRequest,
    registry: AgentRegistry = Depends(get_agent_registry),
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionStateResponse:
    _require_conversational_agent(agent_id, registry)
    try:
        return await session_manager.create_session(
            agent_id=agent_id,
            user_id=body.user_id,
            metadata=body.metadata,
        )
    except AgenticAIError as exc:
        raise _handle_session_errors(exc) from exc


@router.post(
    "/{agent_id}/sessions/{session_id}/messages",
    response_model=AgentResponse,
)
async def continue_session(
    agent_id: str,
    session_id: str,
    body: ContinueSessionRequest,
    registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentResponse:
    _require_conversational_agent(agent_id, registry)
    outer = registry.get(agent_id)
    request = AgentRequest(
        message=body.message,
        user_id=body.user_id,
        session_id=session_id,
        include_transcript=body.include_transcript,
        metadata=body.metadata,
    )
    try:
        return await outer.run(request)
    except AgenticAIError as exc:
        logger.warning("session_continue_failed", agent_id=agent_id, session_id=session_id)
        raise _handle_session_errors(exc) from exc


@router.get("/{agent_id}/sessions/{session_id}", response_model=SessionStateResponse)
async def get_session_state(
    agent_id: str,
    session_id: str,
    include_turns: bool = Query(default=False, description="Include raw turn history"),
    registry: AgentRegistry = Depends(get_agent_registry),
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionStateResponse:
    _require_conversational_agent(agent_id, registry)
    try:
        state = await session_manager.get_session_state(session_id, include_turns=include_turns)
    except AgenticAIError as exc:
        raise _handle_session_errors(exc) from exc

    if state.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found for agent '{agent_id}'",
        )
    return state


@router.delete("/{agent_id}/sessions/{session_id}", response_model=SessionStateResponse)
async def close_session(
    agent_id: str,
    session_id: str,
    registry: AgentRegistry = Depends(get_agent_registry),
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionStateResponse:
    agent = _require_conversational_agent(agent_id, registry)
    try:
        state = await session_manager.get_session_state(session_id)
        if state.agent_id != agent_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found for agent '{agent_id}'",
            )
        return await agent.close_session(session_id)
    except AgenticAIError as exc:
        raise _handle_session_errors(exc) from exc
