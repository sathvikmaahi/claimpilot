"""Framework-level adapter for ADK short-term and long-term memory."""

from __future__ import annotations

from typing import Any

import structlog
from google.adk.memory.base_memory_service import BaseMemoryService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService

from core.config import Settings
from core.conversation.models import ConversationSession, SessionSummary

logger = structlog.get_logger(__name__)


class FrameworkMemoryAdapter:
    """Bridges conversation sessions to ADK memory services."""

    def __init__(
        self,
        *,
        memory_service: BaseMemoryService,
        app_name: str,
        enabled: bool = True,
    ) -> None:
        self._memory = memory_service
        self._app_name = app_name
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def search_relevant(
        self,
        *,
        user_id: str,
        query: str,
        limit: int = 3,
    ) -> list[str]:
        if not self._enabled or not query.strip():
            return []

        try:
            response = await self._memory.search_memory(
                app_name=self._app_name,
                user_id=user_id,
                query=query,
            )
        except Exception:
            logger.exception("memory_search_failed", user_id=user_id)
            return []

        snippets: list[str] = []
        memories = getattr(response, "memories", None) or []
        for entry in memories[:limit]:
            text = getattr(entry, "content", None) or getattr(entry, "text", None)
            if text:
                snippets.append(str(text))
        return snippets

    async def persist_checkpoint(
        self,
        *,
        session: ConversationSession,
        summary: SessionSummary,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._enabled or summary.is_empty():
            return

        try:
            from google.adk.memory.memory_entry import MemoryEntry

            await self._memory.add_memory(
                app_name=self._app_name,
                user_id=session.user_id,
                memories=[
                    MemoryEntry(
                        content=summary.text,  # type: ignore[arg-type]
                        custom_metadata={
                            "session_id": session.session_id,
                            "agent_id": session.agent_id,
                            "turn_count": summary.turn_count,
                            **(metadata or {}),
                        },
                    )
                ],
            )
        except Exception:
            logger.exception(
                "memory_checkpoint_failed",
                session_id=session.session_id,
                user_id=session.user_id,
            )

    async def persist_turn_highlight(
        self,
        *,
        session: ConversationSession,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Persist a concise turn highlight for long-term retrieval."""
        if not self._enabled:
            return

        highlight = f"User: {user_message[:200]} | Assistant: {assistant_message[:200]}"
        try:
            from google.adk.memory.memory_entry import MemoryEntry

            await self._memory.add_memory(
                app_name=self._app_name,
                user_id=session.user_id,
                memories=[
                    MemoryEntry(
                        content=highlight,  # type: ignore[arg-type]
                        custom_metadata={
                            "session_id": session.session_id,
                            "agent_id": session.agent_id,
                            "type": "turn_highlight",
                        },
                    )
                ],
            )
        except Exception:
            logger.exception("memory_turn_persist_failed", session_id=session.session_id)


def create_memory_adapter(settings: Settings) -> FrameworkMemoryAdapter:
    return FrameworkMemoryAdapter(
        memory_service=InMemoryMemoryService(),  # type: ignore[no-untyped-call]
        app_name=settings.app_name,
        enabled=settings.memory_enabled,
    )
