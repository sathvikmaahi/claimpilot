"""Wraps agents with session-aware conversational behavior."""

from __future__ import annotations

from core.agents.contract import AgentContract, AgentRequest, AgentResponse
from core.conversation.models import SessionStateResponse
from core.conversation.policy import SummarizationPolicy
from core.conversation.session_manager import SessionManager


class SessionAwareAgentWrapper(AgentContract):
    """Adds durable session support to a delegate agent without duplicating agent logic."""

    interaction_mode = "conversational"

    def __init__(
        self,
        delegate: AgentContract,
        *,
        session_manager: SessionManager,
        policy: SummarizationPolicy,
    ) -> None:
        self._delegate = delegate
        self._session_manager = session_manager
        self._policy = policy

    @property
    def agent_id(self) -> str:
        return self._delegate.agent_id

    @property
    def name(self) -> str:
        return self._delegate.name

    @property
    def description(self) -> str:
        return self._delegate.description

    @property
    def summarization_policy(self) -> SummarizationPolicy:
        return self._policy

    async def run(self, request: AgentRequest) -> AgentResponse:
        if request.session_id:
            return await self._session_manager.continue_session(
                agent=self._delegate,
                session_id=request.session_id,
                request=request,
                policy=self._policy,
            )

        session_state = await self._session_manager.create_session(
            agent_id=self.agent_id,
            user_id=request.user_id,
            metadata=request.metadata,
        )
        return await self._session_manager.continue_session(
            agent=self._delegate,
            session_id=session_state.session_id,
            request=request,
            policy=self._policy,
        )

    async def health(self) -> bool:
        return await self._delegate.health()

    async def close_session(self, session_id: str) -> SessionStateResponse:
        return await self._session_manager.close_session(
            session_id,
            policy=self._policy,
        )
