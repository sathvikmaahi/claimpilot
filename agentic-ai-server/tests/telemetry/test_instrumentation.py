"""Tests for automatic agent instrumentation."""

import pytest

from agents.chat_assistant.handler import create_agent_handler
from core.agents.contract import AgentRequest
from core.config import Settings
from db.config import DatabaseConfig, MultiDatabaseSettings
from db.engines import initialize_engines
from db.repositories.telemetry import TelemetryRepository
from db.session import create_session_service
from telemetry.instrumentation import InstrumentedAgentHandler
from telemetry.recorder import TelemetryRecorder
from telemetry.redaction import RedactionPolicy


@pytest.mark.asyncio
async def test_instrumented_agent_records_success(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'tel.db'}"
    initialize_engines(MultiDatabaseSettings(telemetry=DatabaseConfig(url=db_url, enabled=True)))
    repo = TelemetryRepository()
    await repo.ensure_schema()
    recorder = TelemetryRecorder(telemetry_repo=repo, policy=RedactionPolicy.privacy_default())

    settings = Settings(google_api_key="test")
    delegate = create_agent_handler(
        agent_id="chat_assistant",
        settings=settings,
        session_service=create_session_service(settings),
        config={"manifest": "agents/chat_assistant/manifest.yaml"},
    )
    agent = InstrumentedAgentHandler(delegate, recorder)
    response = await agent.run(AgentRequest(message="Hello"))
    assert response.agent_id == "chat_assistant"

    from db.engines import shutdown_engines

    await shutdown_engines()
