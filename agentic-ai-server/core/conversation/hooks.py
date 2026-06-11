"""Automatic session persistence hooks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

from core.conversation.memory_adapter import FrameworkMemoryAdapter
from core.conversation.models import ConversationSession, SessionSummary
from core.conversation.policy import SummarizationPolicy

logger = structlog.get_logger(__name__)


@dataclass
class TurnCompletedEvent:
    session: ConversationSession
    summary: SessionSummary
    user_message: str
    assistant_message: str
    policy: SummarizationPolicy
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionClosedEvent:
    session: ConversationSession
    summary: SessionSummary
    policy: SummarizationPolicy


class SessionHook(ABC):
    @abstractmethod
    async def on_turn_completed(self, event: TurnCompletedEvent) -> None:
        """Called after a successful conversational turn."""

    @abstractmethod
    async def on_session_closed(self, event: SessionClosedEvent) -> None:
        """Called when a session is closed."""


class MemoryPersistenceHook(SessionHook):
    """Automatically persists useful session content into long-term memory."""

    def __init__(self, memory: FrameworkMemoryAdapter) -> None:
        self._memory = memory

    async def on_turn_completed(self, event: TurnCompletedEvent) -> None:
        if not event.policy.persist_to_long_term_memory:
            return
        await self._memory.persist_turn_highlight(
            session=event.session,
            user_message=event.user_message,
            assistant_message=event.assistant_message,
        )

    async def on_session_closed(self, event: SessionClosedEvent) -> None:
        if not event.policy.checkpoint_on_close:
            return
        await self._memory.persist_checkpoint(
            session=event.session,
            summary=event.summary,
            metadata={"event": "session_closed"},
        )


class SummarizationCheckpointHook(SessionHook):
    """Ensures summary checkpoints are persisted to long-term memory at intervals."""

    def __init__(self, memory: FrameworkMemoryAdapter) -> None:
        self._memory = memory

    async def on_turn_completed(self, event: TurnCompletedEvent) -> None:
        if not event.policy.persist_to_long_term_memory:
            return
        if event.summary.turn_count > 0 and event.summary.turn_count % (
            event.policy.summarize_every_n_turns * 2
        ) == 0:
            await self._memory.persist_checkpoint(
                session=event.session,
                summary=event.summary,
                metadata={"event": "summary_checkpoint"},
            )

    async def on_session_closed(self, event: SessionClosedEvent) -> None:
        return


def build_default_hooks(memory: FrameworkMemoryAdapter) -> list[SessionHook]:
    return [
        MemoryPersistenceHook(memory),
        SummarizationCheckpointHook(memory),
    ]


class HookRunner:
    def __init__(self, hooks: list[SessionHook]) -> None:
        self._hooks = hooks

    async def emit_turn_completed(self, event: TurnCompletedEvent) -> None:
        for hook in self._hooks:
            try:
                await hook.on_turn_completed(event)
            except Exception:
                logger.exception("session_hook_failed", hook=hook.__class__.__name__)

    async def emit_session_closed(self, event: SessionClosedEvent) -> None:
        for hook in self._hooks:
            try:
                await hook.on_session_closed(event)
            except Exception:
                logger.exception("session_hook_failed", hook=hook.__class__.__name__)
