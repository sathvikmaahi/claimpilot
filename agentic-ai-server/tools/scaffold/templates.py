"""Template rendering for agent scaffolding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class AgentTemplate(StrEnum):
    SIMPLE = "simple"
    CHAT_SYSTEM = "chat-system"
    WORKFLOW_SYSTEM = "workflow-system"


@dataclass
class ScaffoldOptions:
    agent_id: str
    name: str
    description: str
    template: AgentTemplate
    model: str = "gemini-2.0-flash"
    conversational: bool = False


def render_init() -> str:
    return ""


def render_agent_py(opts: ScaffoldOptions) -> str:
    instruction = (
        f"You are {opts.name}. {opts.description}"
    )
    return f'''"""ADK root agent for {opts.agent_id}."""

from google.adk import Agent

root_agent = Agent(
    name="{opts.agent_id}",
    model="{opts.model}",
    instruction="{instruction}",
)
'''


def render_simple_handler(opts: ScaffoldOptions) -> str:
    return f'''"""Handler factory for {opts.agent_id}."""

from __future__ import annotations

from typing import Any

from google.adk import Agent
from google.adk.sessions.base_session_service import BaseSessionService

from agents.{opts.agent_id}.agent import root_agent
from core.agents.adk_adapter import ADKAgentHandler
from core.config import Settings


def create_agent_handler(
    *,
    agent_id: str,
    settings: Settings,
    session_service: BaseSessionService,
    config: dict[str, Any],
) -> ADKAgentHandler:
    adk_config = config.get("adk", {{}})
    model = adk_config.get("model", "{opts.model}")
    instruction = adk_config.get("instruction", root_agent.instruction)

    agent = Agent(name=agent_id, model=model, instruction=instruction)
    return ADKAgentHandler(
        agent_id=agent_id,
        name=str(config.get("name", agent_id)),
        description=config.get("description", ""),
        root_agent=agent,
        session_service=session_service,
        app_name=settings.app_name,
    )
'''


def render_system_manifest(opts: ScaffoldOptions) -> str:
    if opts.template == AgentTemplate.CHAT_SYSTEM:
        return f'''id: {opts.agent_id}
name: {opts.name}
description: {opts.description}

model:
  default: {opts.model}

nodes:
  orchestrator:
    role: orchestrator
    instruction: Classify user intent as chat or task.
    output_key: route
  conversational:
    role: conversational
    instruction: Respond helpfully to conversational messages.
  task_worker:
    role: task
    instruction: Execute actionable user requests step by step.
  session_memory:
    role: memory
    instruction: Summarize the interaction in one sentence.

graph:
  - type: sequential
    steps:
      - orchestrator
      - type: router
        source: orchestrator
        field: route
        routes:
          chat: conversational
          task: task_worker
          default: conversational
      - session_memory
'''
    return f'''id: {opts.agent_id}
name: {opts.name}
description: {opts.description}

model:
  default: {opts.model}

nodes:
  intake:
    role: orchestrator
    instruction: Parse the inbound request and extract structured fields.
    output_key: request_id
  validate:
    role: task
    instruction: Validate required fields and business rules.
    output_key: valid
  processor:
    role: task
    instruction: Process the validated request.
  summarize:
    role: memory
    instruction: Produce a final workflow summary.

graph:
  - type: sequential
    steps:
      - intake
      - type: retry
        max_attempts: 3
        inner:
          type: node
          node: validate
      - processor
      - summarize
'''


def render_system_handler(opts: ScaffoldOptions) -> str:
    if opts.template == AgentTemplate.CHAT_SYSTEM:
        role_map = {
            "orchestrator": "ORCHESTRATOR",
            "conversational": "CONVERSATIONAL",
            "task_worker": "TASK",
            "session_memory": "MEMORY",
        }
        nodes = list(role_map.keys())
    else:
        role_map = {
            "intake": "ORCHESTRATOR",
            "validate": "TASK",
            "processor": "TASK",
            "summarize": "MEMORY",
        }
        nodes = list(role_map.keys())

    handlers = "\n\n".join(
        f'''async def _{node}_handler(context: OrchestrationContext) -> SubAgentResult:
    return SubAgentResult(
        node_id="{node}",
        role=AgentRole.{role_map[node]},
        status=SubAgentStatus.SUCCESS,
        message=f"[{node}] processed: {{context.user_message}}",
        structured={{"status": "ok"}},
    )'''
        for node in nodes
    )
    overrides = ",\n        ".join(
        f'"{n}": FunctionSubAgent('
        f'node_id="{n}", role=AgentRole.{role_map[n]}, handler=_{n}_handler)'
        for n in nodes
    )
    return f'''"""Handler factory for multi-agent system {opts.agent_id}."""

from __future__ import annotations

from typing import Any

from google.adk.sessions.base_session_service import BaseSessionService

from core.composition.context import OrchestrationContext, SubAgentResult, SubAgentStatus
from core.composition.factory import create_agent_system_handler
from core.composition.nodes import FunctionSubAgent
from core.composition.roles import AgentRole
from core.config import Settings

{handlers}


def _demo_node_overrides() -> dict[str, FunctionSubAgent]:
    return {{
        {overrides},
    }}


def create_agent_handler(
    *,
    agent_id: str,
    settings: Settings,
    session_service: BaseSessionService,
    config: dict[str, Any],
):
    return create_agent_system_handler(
        agent_id=agent_id,
        settings=settings,
        session_service=session_service,
        config=config,
        node_overrides=_demo_node_overrides(),
    )
'''


def render_test(opts: ScaffoldOptions) -> str:
    if opts.template == AgentTemplate.SIMPLE:
        return f'''"""Generated tests for {opts.agent_id}."""

import pytest

from core.agents.contract import AgentRequest
from core.config import Settings
from core.agents.loader import build_registry
from core.conversation.factory import create_session_manager
from db.repositories.telemetry import TelemetryRepository
from telemetry.recorder import TelemetryRecorder
from telemetry.redaction import RedactionPolicy


@pytest.mark.unit
def test_{opts.agent_id}_registered():
    settings = Settings(agent_registry_path="agents/registry.yaml", otel_enabled=False)
    registry = build_registry(
        settings,
        session_manager=create_session_manager(settings),
        telemetry_recorder=TelemetryRecorder(
            telemetry_repo=TelemetryRepository(),
            policy=RedactionPolicy.privacy_default(),
        ),
    )
    assert "{opts.agent_id}" in registry.list_ids()


@pytest.mark.api
def test_{opts.agent_id}_run_endpoint(client):
    response = client.post(
        "/agents/{opts.agent_id}/run",
        json={{"message": "hello"}},
    )
    assert response.status_code in {{200, 502}}
'''
    return f'''"""Generated tests for agent system {opts.agent_id}."""

import pytest

from core.config import Settings
from core.agents.loader import build_registry
from core.conversation.factory import create_session_manager
from db.repositories.telemetry import TelemetryRepository
from telemetry.recorder import TelemetryRecorder
from telemetry.redaction import RedactionPolicy


@pytest.mark.unit
def test_{opts.agent_id}_registered():
    settings = Settings(agent_registry_path="agents/registry.yaml", otel_enabled=False)
    registry = build_registry(
        settings,
        session_manager=create_session_manager(settings),
        telemetry_recorder=TelemetryRecorder(
            telemetry_repo=TelemetryRepository(),
            policy=RedactionPolicy.privacy_default(),
        ),
    )
    assert "{opts.agent_id}" in registry.list_ids()


@pytest.mark.orchestration
@pytest.mark.asyncio
async def test_{opts.agent_id}_system_runs():
    from agents.{opts.agent_id}.handler import create_agent_handler
    from core.agents.contract import AgentRequest
    from db.session import create_session_service

    settings = Settings(google_api_key="test", otel_enabled=False)
    handler = create_agent_handler(
        agent_id="{opts.agent_id}",
        settings=settings,
        session_service=create_session_service(settings),
        config={{"manifest": "agents/{opts.agent_id}/manifest.yaml"}},
    )
    response = await handler.run(AgentRequest(message="test request"))
    assert response.agent_id == "{opts.agent_id}"
    assert response.message
'''


def render_registry_entry(opts: ScaffoldOptions) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": opts.agent_id,
        "enabled": True,
        "name": opts.name,
        "description": opts.description,
        "handler_module": f"agents.{opts.agent_id}.handler",
        "handler_class": "create_agent_handler",
    }
    if opts.template == AgentTemplate.SIMPLE:
        entry["adk"] = {
            "model": opts.model,
            "instruction": f"You are {opts.name}. {opts.description}",
        }
    else:
        entry["type"] = "agent_system"
        entry["manifest"] = f"agents/{opts.agent_id}/manifest.yaml"
        entry["interaction_mode"] = "conversational" if opts.conversational else "stateless"
        if opts.conversational:
            entry["conversation"] = {
                "summarize_every_n_turns": 2,
                "recent_turns_window": 2,
                "max_summary_chars": 1500,
            }
    return entry
