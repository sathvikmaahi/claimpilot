"""Tests for manifest loading and graph building."""

from core.composition.builder import build_pipeline, load_agent_system_manifest
from core.composition.roles import AgentRole
from core.config import Settings
from db.session import create_session_service


def test_load_chat_assistant_manifest():
    manifest = load_agent_system_manifest("agents/chat_assistant/manifest.yaml")
    assert manifest.id == "chat_assistant"
    assert "orchestrator" in manifest.nodes
    assert manifest.nodes["orchestrator"].role == AgentRole.ORCHESTRATOR
    assert len(manifest.graph) == 1


def test_build_pipeline_from_manifest():
    settings = Settings(google_api_key="test")
    session_service = create_session_service(settings)
    manifest = load_agent_system_manifest("agents/chat_assistant/manifest.yaml")
    pipeline = build_pipeline(manifest, settings, session_service)
    assert pipeline is not None
