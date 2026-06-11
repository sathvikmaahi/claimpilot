"""Session service factory for stateless Cloud Run deployments."""

from __future__ import annotations

import structlog
from google.adk.sessions.base_session_service import BaseSessionService
from google.adk.sessions.in_memory_session_service import InMemorySessionService

from core.config import Settings

logger = structlog.get_logger(__name__)


def create_session_service(settings: Settings) -> BaseSessionService:
    """Return a session backend appropriate for the current environment.

    When ``SESSION_SERVICE_URI`` is set, ADK-compatible persistent storage
    (e.g. SQLite, PostgreSQL, Vertex AI) can be wired here. For local
    development and stateless Cloud Run cold starts, in-memory is the default.
    """
    if settings.session_service_uri:
        logger.warning(
            "session_service_uri_configured_but_not_implemented",
            uri=settings.session_service_uri,
            fallback="InMemorySessionService",
        )

    return InMemorySessionService()  # type: ignore[no-untyped-call]
