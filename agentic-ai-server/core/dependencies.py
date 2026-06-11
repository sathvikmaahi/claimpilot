"""FastAPI dependency injection helpers."""

from functools import lru_cache

from core.agents.loader import build_registry
from core.agents.registry import AgentRegistry
from core.config import Settings, get_settings
from core.conversation.factory import create_session_manager
from core.conversation.session_manager import SessionManager
from db.repositories.telemetry import AnalyticsRepository, TelemetryRepository
from telemetry.recorder import TelemetryRecorder
from telemetry.redaction import RedactionPolicy


@lru_cache
def get_session_manager() -> SessionManager:
    return create_session_manager(get_settings())


@lru_cache
def get_telemetry_repository() -> TelemetryRepository:
    return TelemetryRepository()


@lru_cache
def get_analytics_repository() -> AnalyticsRepository:
    return AnalyticsRepository()


@lru_cache
def get_telemetry_recorder() -> TelemetryRecorder:
    settings = get_settings()
    return TelemetryRecorder(
        telemetry_repo=get_telemetry_repository(),
        analytics_repo=get_analytics_repository(),
        policy=RedactionPolicy.from_settings(settings),
    )


@lru_cache
def get_agent_registry() -> AgentRegistry:
    settings = get_settings()
    return build_registry(
        settings,
        session_manager=get_session_manager(),
        telemetry_recorder=get_telemetry_recorder(),
    )


def get_settings_dep() -> Settings:
    return get_settings()
