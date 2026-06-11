"""Factory helpers for declarative agent-system registration."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from google.adk.sessions.base_session_service import BaseSessionService

from core.composition.builder import build_pipeline, load_agent_system_manifest
from core.composition.handler import AgentSystemHandler
from core.composition.nodes import SubAgent
from core.config import Settings


def create_agent_system_handler(
    *,
    agent_id: str,
    settings: Settings,
    session_service: BaseSessionService,
    config: dict[str, Any],
    node_overrides: Mapping[str, SubAgent] | None = None,
) -> AgentSystemHandler:
    """Build a deployable agent system from registry config or manifest path."""
    manifest_path = config.get("manifest") or f"agents/{agent_id}/manifest.yaml"
    manifest = load_agent_system_manifest(Path(manifest_path))

    if manifest.id != agent_id:
        manifest = manifest.model_copy(update={"id": agent_id})

    pipeline = build_pipeline(
        manifest,
        settings,
        session_service,
        node_overrides=node_overrides,
    )
    return AgentSystemHandler(manifest=manifest, pipeline=pipeline)
