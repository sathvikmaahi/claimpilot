"""Session persistence abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.conversation.models import (
    ConversationSession,
    ConversationTurn,
    SessionStatus,
    SessionSummary,
    utc_now,
)


class ConversationSessionStore(ABC):
    """Centralized store for session metadata, turns, summaries, and user state."""

    @abstractmethod
    async def create_session(
        self,
        *,
        agent_id: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationSession:
        """Create a new active session."""

    @abstractmethod
    async def get_session(self, session_id: str) -> ConversationSession | None:
        """Load session metadata."""

    @abstractmethod
    async def update_session(self, session: ConversationSession) -> ConversationSession:
        """Persist session metadata and user state."""

    @abstractmethod
    async def append_turn(self, session_id: str, turn: ConversationTurn) -> ConversationTurn:
        """Append a turn to session history."""

    @abstractmethod
    async def get_turns(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ConversationTurn]:
        """Return turns ordered by turn_index."""

    @abstractmethod
    async def get_turn_count(self, session_id: str) -> int:
        """Return total number of stored turns."""

    @abstractmethod
    async def get_summary(self, session_id: str) -> SessionSummary:
        """Return the current rolling summary for a session."""

    @abstractmethod
    async def save_summary(self, summary: SessionSummary) -> SessionSummary:
        """Persist an updated rolling summary."""

    async def close_session(self, session_id: str) -> ConversationSession:
        session = await self.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        session.status = SessionStatus.CLOSED
        session.closed_at = utc_now()
        session.updated_at = utc_now()
        return await self.update_session(session)
