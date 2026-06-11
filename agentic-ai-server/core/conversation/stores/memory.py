"""In-memory session store for local development and tests."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from core.conversation.models import (
    ConversationSession,
    ConversationTurn,
    SessionSummary,
    utc_now,
)
from core.conversation.session_store import ConversationSessionStore


class InMemoryConversationSessionStore(ConversationSessionStore):
    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}
        self._turns: dict[str, list[ConversationTurn]] = {}
        self._summaries: dict[str, SessionSummary] = {}

    async def create_session(
        self,
        *,
        agent_id: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationSession:
        session = ConversationSession(
            session_id=str(uuid4()),
            agent_id=agent_id,
            user_id=user_id,
            metadata=metadata or {},
        )
        self._sessions[session.session_id] = session
        self._turns[session.session_id] = []
        self._summaries[session.session_id] = SessionSummary(
            session_id=session.session_id,
            text="",
            turn_count=0,
        )
        return session

    async def get_session(self, session_id: str) -> ConversationSession | None:
        return self._sessions.get(session_id)

    async def update_session(self, session: ConversationSession) -> ConversationSession:
        session.updated_at = utc_now()
        self._sessions[session.session_id] = session
        return session

    async def append_turn(self, session_id: str, turn: ConversationTurn) -> ConversationTurn:
        self._turns.setdefault(session_id, []).append(turn)
        session = self._sessions.get(session_id)
        if session:
            session.updated_at = utc_now()
        return turn

    async def get_turns(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ConversationTurn]:
        turns = self._turns.get(session_id, [])
        sliced = turns[offset:]
        if limit is not None:
            return sliced[:limit]
        return sliced

    async def get_turn_count(self, session_id: str) -> int:
        return len(self._turns.get(session_id, []))

    async def get_summary(self, session_id: str) -> SessionSummary:
        return self._summaries.get(
            session_id,
            SessionSummary(session_id=session_id, text="", turn_count=0),
        )

    async def save_summary(self, summary: SessionSummary) -> SessionSummary:
        summary.updated_at = utc_now()
        self._summaries[summary.session_id] = summary
        return summary
