"""Agent registry tests."""

from core.agents.loader import build_registry
from core.config import Settings
from core.conversation.factory import create_session_manager
from core.conversation.wrapper import SessionAwareAgentWrapper
from db.repositories.telemetry import TelemetryRepository
from telemetry.instrumentation import InstrumentedAgentHandler
from telemetry.recorder import TelemetryRecorder
from telemetry.redaction import RedactionPolicy


def _build_test_registry(settings: Settings):
    session_manager = create_session_manager(settings)
    recorder = TelemetryRecorder(
        telemetry_repo=TelemetryRepository(),
        policy=RedactionPolicy.from_settings(settings),
    )
    return build_registry(settings, session_manager=session_manager, telemetry_recorder=recorder)


def test_registry_loads_echo_agent():
    settings = Settings(
        agent_registry_path="agents/registry.yaml",
        google_api_key="test-key",
        otel_enabled=False,
    )
    registry = _build_test_registry(settings)
    assert "echo" in registry.list_ids()
    assert "chat_assistant" in registry.list_ids()
    assert "claim_workflow" in registry.list_ids()

    agent = registry.get("echo")
    assert agent.name == "Echo Agent"
    assert agent.description


def test_registry_loads_agent_systems():
    settings = Settings(
        agent_registry_path="agents/registry.yaml",
        google_api_key="test-key",
        otel_enabled=False,
    )
    registry = _build_test_registry(settings)
    chat = registry.get("chat_assistant")
    assert chat.agent_id == "chat_assistant"
    assert isinstance(chat, InstrumentedAgentHandler)
    inner = chat._delegate  # noqa: SLF001
    assert isinstance(inner, SessionAwareAgentWrapper)

    workflow = registry.get("claim_workflow")
    assert getattr(workflow, "interaction_mode", "stateless") == "stateless"
