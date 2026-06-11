"""Domain models for the conversation layer."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class SessionStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class TurnRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class SessionSummary(BaseModel):
    """First-class rolling summary artifact for a conversation session."""

    session_id: str
    text: str = ""
    turn_count: int = 0
    updated_at: datetime = Field(default_factory=utc_now)

    def is_empty(self) -> bool:
        return not self.text.strip()


class ConversationTurn(BaseModel):
    """A single turn in session history."""

    turn_index: int
    role: TurnRole
    content: str
    created_at: datetime = Field(default_factory=utc_now)


class ConversationSession(BaseModel):
    """Session metadata and mutable user state."""

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    user_id: str
    status: SessionStatus = SessionStatus.ACTIVE
    user_state: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    closed_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status == SessionStatus.ACTIVE


class PreparedConversationContext(BaseModel):
    """Context injected into agent runs — summary-first, not full transcript."""

    session: ConversationSession
    summary: SessionSummary
    recent_turns: list[ConversationTurn] = Field(default_factory=list)
    memory_snippets: list[str] = Field(default_factory=list)

    @property
    def session_id(self) -> str:
        return self.session.session_id


class SessionStateResponse(BaseModel):
    """Public session state returned by REST endpoints."""

    session_id: str
    agent_id: str
    user_id: str
    status: SessionStatus
    summary: SessionSummary
    turn_count: int
    user_state: dict[str, Any] = Field(default_factory=dict)
    recent_turns: list[ConversationTurn] | None = None
