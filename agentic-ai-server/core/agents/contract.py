"""Shared request/response models and agent contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class AgentRequest(BaseModel):
    """Normalized inbound payload for every exposed agent."""

    message: str = Field(..., min_length=1, description="User message to send to the agent")
    user_id: str = Field(default="anonymous", description="Stable user identifier for sessions")
    session_id: str | None = Field(
        default=None,
        description="Existing session ID; a new session is created when omitted",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    include_transcript: bool = Field(
        default=False,
        description="When true, include full transcript in agent context (opt-in only)",
    )
    conversation_context: dict[str, Any] | None = Field(
        default=None,
        description="Injected summary-first conversation context from SessionManager",
    )


class AgentResponse(BaseModel):
    """Normalized outbound payload returned by every agent."""

    agent_id: str
    session_id: str
    message: str
    events: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentContract(ABC):
    """Interface every top-level agent must implement for API registration."""

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """Unique slug used in REST paths (e.g. /agents/{agent_id}/run)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable agent name."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description surfaced in discovery endpoints."""

    @abstractmethod
    async def run(self, request: AgentRequest) -> AgentResponse:
        """Execute the agent and return a shaped response."""

    async def health(self) -> bool:
        """Optional readiness probe for agent-specific dependencies."""
        return True
