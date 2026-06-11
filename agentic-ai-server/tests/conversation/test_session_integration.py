"""Integration tests for session-aware conversational agents."""

import pytest
from fastapi.testclient import TestClient

from agents.chat_assistant.handler import create_agent_handler
from core.agents.contract import AgentRequest
from core.config import Settings
from core.conversation.factory import create_session_manager
from core.conversation.policy import SummarizationPolicy
from core.conversation.wrapper import SessionAwareAgentWrapper
from db.session import create_session_service


@pytest.fixture
def chat_agent():
    settings = Settings(google_api_key="test", memory_enabled=True)
    session_service = create_session_service(settings)
    delegate = create_agent_handler(
        agent_id="chat_assistant",
        settings=settings,
        session_service=session_service,
        config={"manifest": "agents/chat_assistant/manifest.yaml"},
    )
    return SessionAwareAgentWrapper(
        delegate,
        session_manager=create_session_manager(settings),
        policy=SummarizationPolicy(summarize_every_n_turns=2, recent_turns_window=1),
    )


@pytest.mark.asyncio
async def test_session_continues_with_summary_not_full_replay(chat_agent):
    first = await chat_agent.run(AgentRequest(message="Hello!", user_id="u1"))
    session_id = first.session_id

    second = await chat_agent.run(
        AgentRequest(message="Tell me more", user_id="u1", session_id=session_id)
    )
    assert second.session_id == session_id
    assert second.metadata["conversation"]["summary_turn_count"] >= 2
    assert second.metadata["conversation"]["transcript_replayed"] is False


@pytest.mark.asyncio
async def test_close_session(chat_agent):
    response = await chat_agent.run(AgentRequest(message="Hi", user_id="u1"))
    closed = await chat_agent.close_session(response.session_id)
    assert closed.status.value == "closed"


def test_session_rest_endpoints(client: TestClient):
    created = client.post(
        "/agents/chat_assistant/sessions",
        json={"user_id": "rest-user"},
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    continued = client.post(
        f"/agents/chat_assistant/sessions/{session_id}/messages",
        json={"message": "Hello via REST", "user_id": "rest-user"},
    )
    assert continued.status_code == 200
    assert continued.json()["session_id"] == session_id

    state = client.get(f"/agents/chat_assistant/sessions/{session_id}")
    assert state.status_code == 200
    assert state.json()["turn_count"] == 2
    assert "summary" in state.json()

    closed = client.delete(f"/agents/chat_assistant/sessions/{session_id}")
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"


def test_stateless_agent_rejects_session_api(client: TestClient):
    response = client.post(
        "/agents/claim_workflow/sessions",
        json={"user_id": "u1"},
    )
    assert response.status_code == 400
