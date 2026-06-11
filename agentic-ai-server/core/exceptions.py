"""Shared exception types for agent execution and API responses."""

from typing import Any


class AgenticAIError(Exception):
    """Base exception for the service."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AgentNotFoundError(AgenticAIError):
    """Raised when a requested agent is not registered."""


class AgentExecutionError(AgenticAIError):
    """Raised when an agent fails during execution."""


class AgentConfigurationError(AgenticAIError):
    """Raised when agent configuration or loading fails."""


class SessionNotFoundError(AgenticAIError):
    """Raised when a conversation session does not exist."""


class SessionClosedError(AgenticAIError):
    """Raised when operating on a closed conversation session."""
