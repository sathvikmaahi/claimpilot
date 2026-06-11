"""SQLite-backed session store for production deployments."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite

from core.conversation.models import (
    ConversationSession,
    ConversationTurn,
    SessionStatus,
    SessionSummary,
    TurnRole,
    utc_now,
)
from core.conversation.session_store import ConversationSessionStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_sessions (
    session_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    user_state TEXT NOT NULL DEFAULT '{}',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS conversation_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES conversation_sessions(session_id)
);

CREATE TABLE IF NOT EXISTS session_summaries (
    session_id TEXT PRIMARY KEY,
    summary_text TEXT NOT NULL DEFAULT '',
    turn_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES conversation_sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON conversation_turns(session_id, turn_index);
"""


def _dt_iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SqliteConversationSessionStore(ConversationSessionStore):
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    async def _ensure_schema(self) -> None:
        if self._initialized:
            return
        conn = await aiosqlite.connect(self._database_path)
        try:
            await conn.executescript(_SCHEMA)
            await conn.commit()
        finally:
            await conn.close()
        self._initialized = True

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[aiosqlite.Connection]:
        await self._ensure_schema()
        conn = await aiosqlite.connect(self._database_path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()

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
        summary = SessionSummary(session_id=session.session_id, text="", turn_count=0)
        async with self._connection() as conn:
            await conn.execute(
                """
                INSERT INTO conversation_sessions
                (session_id, agent_id, user_id, status, user_state, metadata,
                 created_at, updated_at, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.agent_id,
                    session.user_id,
                    session.status.value,
                    json.dumps(session.user_state),
                    json.dumps(session.metadata),
                    _dt_iso(session.created_at),
                    _dt_iso(session.updated_at),
                    None,
                ),
            )
            await conn.execute(
                """
                INSERT INTO session_summaries (session_id, summary_text, turn_count, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    summary.session_id,
                    summary.text,
                    summary.turn_count,
                    _dt_iso(summary.updated_at),
                ),
            )
            await conn.commit()
        return session

    async def get_session(self, session_id: str) -> ConversationSession | None:
        async with self._connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM conversation_sessions WHERE session_id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return ConversationSession(
            session_id=row["session_id"],
            agent_id=row["agent_id"],
            user_id=row["user_id"],
            status=SessionStatus(row["status"]),
            user_state=json.loads(row["user_state"]),
            metadata=json.loads(row["metadata"]),
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
            closed_at=_parse_dt(row["closed_at"]) if row["closed_at"] else None,
        )

    async def update_session(self, session: ConversationSession) -> ConversationSession:
        session.updated_at = utc_now()
        async with self._connection() as conn:
            await conn.execute(
                """
                UPDATE conversation_sessions
                SET status = ?, user_state = ?, metadata = ?, updated_at = ?, closed_at = ?
                WHERE session_id = ?
                """,
                (
                    session.status.value,
                    json.dumps(session.user_state),
                    json.dumps(session.metadata),
                    _dt_iso(session.updated_at),
                    _dt_iso(session.closed_at) if session.closed_at else None,
                    session.session_id,
                ),
            )
            await conn.commit()
        return session

    async def append_turn(self, session_id: str, turn: ConversationTurn) -> ConversationTurn:
        async with self._connection() as conn:
            await conn.execute(
                """
                INSERT INTO conversation_turns
                (session_id, turn_index, role, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    turn.turn_index,
                    turn.role.value,
                    turn.content,
                    _dt_iso(turn.created_at),
                ),
            )
            await conn.execute(
                "UPDATE conversation_sessions SET updated_at = ? WHERE session_id = ?",
                (_dt_iso(utc_now()), session_id),
            )
            await conn.commit()
        return turn

    async def get_turns(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ConversationTurn]:
        if limit is not None:
            query = """
                SELECT turn_index, role, content, created_at
                FROM conversation_turns
                WHERE session_id = ?
                ORDER BY turn_index ASC
                LIMIT ? OFFSET ?
            """
            params: tuple[Any, ...] = (session_id, limit, offset)
        elif offset > 0:
            query = """
                SELECT turn_index, role, content, created_at
                FROM conversation_turns
                WHERE session_id = ?
                ORDER BY turn_index ASC
                LIMIT -1 OFFSET ?
            """
            params = (session_id, offset)
        else:
            query = """
                SELECT turn_index, role, content, created_at
                FROM conversation_turns
                WHERE session_id = ?
                ORDER BY turn_index ASC
            """
            params = (session_id,)

        async with self._connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
        return [
            ConversationTurn(
                turn_index=row["turn_index"],
                role=TurnRole(row["role"]),
                content=row["content"],
                created_at=_parse_dt(row["created_at"]),
            )
            for row in rows
        ]

    async def get_turn_count(self, session_id: str) -> int:
        async with self._connection() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) AS cnt FROM conversation_turns WHERE session_id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return 0
        return int(row["cnt"])

    async def get_summary(self, session_id: str) -> SessionSummary:
        async with self._connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM session_summaries WHERE session_id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return SessionSummary(session_id=session_id, text="", turn_count=0)
        return SessionSummary(
            session_id=row["session_id"],
            text=row["summary_text"],
            turn_count=row["turn_count"],
            updated_at=_parse_dt(row["updated_at"]),
        )

    async def save_summary(self, summary: SessionSummary) -> SessionSummary:
        summary.updated_at = utc_now()
        async with self._connection() as conn:
            await conn.execute(
                """
                INSERT INTO session_summaries (session_id, summary_text, turn_count, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    summary_text = excluded.summary_text,
                    turn_count = excluded.turn_count,
                    updated_at = excluded.updated_at
                """,
                (
                    summary.session_id,
                    summary.text,
                    summary.turn_count,
                    _dt_iso(summary.updated_at),
                ),
            )
            await conn.commit()
        return summary
