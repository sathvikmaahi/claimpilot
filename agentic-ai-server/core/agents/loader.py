"""Load and instantiate agents declared in the registry manifest."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml

from core.agents.contract import AgentContract
from core.agents.registry import AgentRegistry
from core.config import Settings
from core.conversation.policy import SummarizationPolicy
from core.conversation.session_manager import SessionManager
from core.conversation.wrapper import SessionAwareAgentWrapper
from core.exceptions import AgentConfigurationError
from db.session import create_session_service
from telemetry.instrumentation import InstrumentedAgentHandler
from telemetry.recorder import TelemetryRecorder


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise AgentConfigurationError(
            f"Agent registry not found: {path}",
            details={"path": str(path)},
        )

    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    agents = data.get("agents", [])
    if not isinstance(agents, list):
        raise AgentConfigurationError("Agent registry 'agents' must be a list")
    return agents


def _import_symbol(module_path: str, symbol: str) -> Any:
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise AgentConfigurationError(
            f"Cannot import module '{module_path}'",
            details={"module": module_path, "error": str(exc)},
        ) from exc

    try:
        return getattr(module, symbol)
    except AttributeError as exc:
        raise AgentConfigurationError(
            f"Symbol '{symbol}' not found in '{module_path}'",
            details={"module": module_path, "symbol": symbol},
        ) from exc


def build_registry(
    settings: Settings,
    session_manager: SessionManager | None = None,
    telemetry_recorder: TelemetryRecorder | None = None,
) -> AgentRegistry:
    """Load all enabled agents from the YAML manifest and register them."""
    registry = AgentRegistry()
    manifest_path = Path(settings.agent_registry_path)
    session_service = create_session_service(settings)

    for entry in _load_manifest(manifest_path):
        if not entry.get("enabled", True):
            continue

        agent_id = entry.get("id")
        handler_module = entry.get("handler_module")
        handler_class = entry.get("handler_class", "create_agent_handler")

        if not agent_id or not handler_module:
            raise AgentConfigurationError(
                "Each agent entry requires 'id' and 'handler_module'",
                details={"entry": entry},
            )

        factory = _import_symbol(handler_module, handler_class)
        agent: AgentContract = factory(
            agent_id=agent_id,
            settings=settings,
            session_service=session_service,
            config=entry,
        )

        if entry.get("interaction_mode") == "conversational" and session_manager is not None:
            policy = SummarizationPolicy.from_config(entry.get("conversation"))
            agent = SessionAwareAgentWrapper(
                agent,
                session_manager=session_manager,
                policy=policy,
            )

        if telemetry_recorder is not None:
            agent = InstrumentedAgentHandler(agent, telemetry_recorder)

        registry.register(agent)

    return registry
