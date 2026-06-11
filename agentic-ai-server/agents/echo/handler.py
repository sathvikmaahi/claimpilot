"""Factory that wires the echo ADK agent into the shared service contract."""

from __future__ import annotations

from typing import Any

from google.adk import Agent
from google.adk.sessions.base_session_service import BaseSessionService

from agents.echo.agent import root_agent
from core.agents.adk_adapter import ADKAgentHandler
from core.config import Settings


def create_agent_handler(
    *,
    agent_id: str,
    settings: Settings,
    session_service: BaseSessionService,
    config: dict[str, Any],
) -> ADKAgentHandler:
    adk_config = config.get("adk", {})
    model = adk_config.get("model", "gemini-2.0-flash")
    instruction = adk_config.get("instruction", root_agent.instruction)

    # ADK node names must be valid Python identifiers; use agent_id for the ADK name.
    agent = Agent(
        name=agent_id,
        model=model,
        instruction=instruction,
    )

    return ADKAgentHandler(
        agent_id=agent_id,
        name=str(config.get("name", agent_id)),
        description=config.get("description", ""),
        root_agent=agent,
        session_service=session_service,
        app_name=settings.app_name,
    )
