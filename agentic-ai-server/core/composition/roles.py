"""Taxonomy of sub-agent roles within a deployable agent system."""

from __future__ import annotations

from enum import StrEnum


class AgentRole(StrEnum):
    """Standard roles for sub-agents in a multi-agent composition."""

    ORCHESTRATOR = "orchestrator"
    """Coordinates child agents and owns the top-level execution plan."""

    CONVERSATIONAL = "conversational"
    """Handles open-ended dialogue with the end user."""

    TASK = "task"
    """Executes a bounded, goal-directed assignment."""

    TOOL_WRAPPER = "tool_wrapper"
    """Wraps an external tool or API with a thin agent interface."""

    ROUTER = "router"
    """Selects which downstream agent should handle the current context."""

    MEMORY = "memory"
    """Summarizes, persists, or retrieves contextual memory."""

    @property
    def description(self) -> str:
        return _ROLE_DESCRIPTIONS[self]


_ROLE_DESCRIPTIONS: dict[AgentRole, str] = {
    AgentRole.ORCHESTRATOR: "Plans and delegates work across the agent graph.",
    AgentRole.CONVERSATIONAL: "Maintains natural multi-turn conversation.",
    AgentRole.TASK: "Completes structured tasks with deterministic outputs.",
    AgentRole.TOOL_WRAPPER: "Invokes tools and normalizes their responses.",
    AgentRole.ROUTER: "Routes context to the appropriate specialist agent.",
    AgentRole.MEMORY: "Manages session memory and summarization.",
}
