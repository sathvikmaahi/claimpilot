"""Orchestrates session lifecycle, summarization, and memory integration."""

from __future__ import annotations

from typing import Any

import structlog

from core.agents.contract import AgentContract, AgentRequest, AgentResponse
from core.conversation.context_builder import (
    build_agent_message,
    build_prepared_context,
    split_user_and_assistant_turns,
)
from core.conversation.hooks import HookRunner, SessionClosedEvent, TurnCompletedEvent
from core.conversation.memory_adapter import FrameworkMemoryAdapter
from core.conversation.models import ConversationSession, SessionStateResponse, SessionStatus
from core.conversation.policy import SummarizationPolicy
from core.conversation.session_store import ConversationSessionStore
from core.conversation.summarizer import SummarizationPipeline
from core.exceptions import SessionClosedError, SessionNotFoundError

logger = structlog.get_logger(__name__)


class SessionManager:
    """Central conversation layer for durable, summary-first chat sessions."""

    def __init__(
        self,
        *,
        store: ConversationSessionStore,
        summarization: SummarizationPipeline,
        memory: FrameworkMemoryAdapter,
        hooks: HookRunner,
    ) -> None:
        self._store = store
        self._summarization = summarization
        self._memory = memory
        self._hooks = hooks

    async def create_session(
        self,
        *,
        agent_id: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> SessionStateResponse:
        session = await self._store.create_session(
            agent_id=agent_id,
            user_id=user_id,
            metadata=metadata,
        )
        summary = await self._store.get_summary(session.session_id)
        return SessionStateResponse(
            session_id=session.session_id,
            agent_id=session.agent_id,
            user_id=session.user_id,
            status=session.status,
            summary=summary,
            turn_count=0,
            user_state=session.user_state,
        )

    async def get_session_state(
        self,
        session_id: str,
        *,
        include_turns: bool = False,
    ) -> SessionStateResponse:
        session = await self._require_active_or_closed(session_id)
        summary = await self._store.get_summary(session_id)
        turn_count = await self._store.get_turn_count(session_id)
        recent_turns = None
        if include_turns:
            recent_turns = await self._store.get_turns(session_id)
        return SessionStateResponse(
            session_id=session.session_id,
            agent_id=session.agent_id,
            user_id=session.user_id,
            status=session.status,
            summary=summary,
            turn_count=turn_count,
            user_state=session.user_state,
            recent_turns=recent_turns,
        )

    async def close_session(
        self,
        session_id: str,
        *,
        policy: SummarizationPolicy,
    ) -> SessionStateResponse:
        session = await self._require_session(session_id)
        if session.status == SessionStatus.CLOSED:
            return await self.get_session_state(session_id)

        all_turns = await self._store.get_turns(session_id)
        summary = await self._store.get_summary(session_id)
        summary = await self._summarization.maybe_update(
            summary=summary,
            all_turns=all_turns,
            policy=policy,
            force=True,
        )
        await self._store.save_summary(summary)
        session = await self._store.close_session(session_id)

        await self._hooks.emit_session_closed(
            SessionClosedEvent(session=session, summary=summary, policy=policy)
        )
        return await self.get_session_state(session_id)

    async def continue_session(
        self,
        *,
        agent: AgentContract,
        session_id: str,
        request: AgentRequest,
        policy: SummarizationPolicy,
    ) -> AgentResponse:
        session = await self._require_active(session_id)
        if session.agent_id != agent.agent_id:
            raise SessionNotFoundError(
                f"Session '{session_id}' belongs to agent '{session.agent_id}'",
                details={"session_id": session_id, "expected_agent": agent.agent_id},
            )

        all_turns = await self._store.get_turns(session_id)
        summary = await self._store.get_summary(session_id)
        memory_snippets: list[str] = []
        if policy.search_long_term_memory:
            memory_snippets = await self._memory.search_relevant(
                user_id=session.user_id,
                query=request.message,
                limit=policy.memory_search_limit,
            )

        prepared = build_prepared_context(
            session=session,
            summary=summary,
            all_turns=all_turns,
            memory_snippets=memory_snippets,
            policy=policy,
        )

        enriched_message = build_agent_message(
            request.message,
            prepared,
            include_transcript=request.include_transcript,
            full_turns=all_turns if request.include_transcript else None,
        )

        agent_request = request.model_copy(
            update={
                "message": enriched_message,
                "session_id": session_id,
                "conversation_context": prepared.model_dump(mode="json"),
            }
        )
        response = await agent.run(agent_request)

        start_index = len(all_turns)
        new_turns = split_user_and_assistant_turns(
            request.message,
            response.message,
            start_index=start_index,
        )
        for turn in new_turns:
            await self._store.append_turn(session_id, turn)

        all_turns = await self._store.get_turns(session_id)
        summary = await self._summarization.maybe_update(
            summary=summary,
            all_turns=all_turns,
            policy=policy,
        )
        await self._store.save_summary(summary)

        await self._hooks.emit_turn_completed(
            TurnCompletedEvent(
                session=session,
                summary=summary,
                user_message=request.message,
                assistant_message=response.message,
                policy=policy,
            )
        )

        response.metadata.update(
            {
                "conversation": {
                    "summary_turn_count": summary.turn_count,
                    "summary_preview": summary.text[:200],
                    "memory_snippets_used": len(memory_snippets),
                    "transcript_replayed": request.include_transcript,
                }
            }
        )
        return response.model_copy(update={"session_id": session_id})

    async def _require_session(self, session_id: str) -> ConversationSession:
        session = await self._store.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(
                f"Session '{session_id}' not found",
                details={"session_id": session_id},
            )
        return session

    async def _require_active(self, session_id: str) -> ConversationSession:
        session = await self._require_session(session_id)
        if not session.is_active:
            raise SessionClosedError(
                f"Session '{session_id}' is closed",
                details={"session_id": session_id},
            )
        return session

    async def _require_active_or_closed(self, session_id: str) -> ConversationSession:
        return await self._require_session(session_id)
