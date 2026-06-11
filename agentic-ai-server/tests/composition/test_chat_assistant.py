"""Integration tests for the chat-oriented agent system."""

import pytest

from agents.chat_assistant.handler import create_agent_handler
from core.agents.contract import AgentRequest
from core.config import Settings
from db.session import create_session_service


@pytest.fixture
def chat_handler():
    settings = Settings(google_api_key="test")
    session_service = create_session_service(settings)
    return create_agent_handler(
        agent_id="chat_assistant",
        settings=settings,
        session_service=session_service,
        config={"manifest": "agents/chat_assistant/manifest.yaml"},
    )


@pytest.mark.asyncio
async def test_chat_routes_to_conversational(chat_handler):
    response = await chat_handler.run(AgentRequest(message="Hello there!"))
    assert response.agent_id == "chat_assistant"
    assert "conversational" in response.metadata["trace"]
    assert "session_memory" in response.metadata["trace"]
    assert response.metadata["route"]["selected"] == "conversational"


@pytest.mark.asyncio
async def test_chat_routes_to_task_worker(chat_handler):
    response = await chat_handler.run(AgentRequest(message="Please submit my claim"))
    assert response.metadata["route"]["selected"] == "task_worker"
    assert any(event["node_id"] == "task_worker" for event in response.events)
