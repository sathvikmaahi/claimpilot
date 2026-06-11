"""Application startup and shutdown hooks."""

from __future__ import annotations

import structlog
from fastapi import FastAPI

from core.config import Settings
from core.dependencies import get_agent_registry, get_session_manager, get_telemetry_recorder
from core.security.secrets import load_runtime_secrets
from db.config import MultiDatabaseSettings
from db.factory import initialize_databases, shutdown_databases
from telemetry.logging import configure_logging
from telemetry.setup import configure_observability, instrument_fastapi

logger = structlog.get_logger(__name__)


async def on_startup(app: FastAPI, settings: Settings) -> None:
    configure_logging(settings)
    configure_observability(settings)
    instrument_fastapi(app, settings)
    load_runtime_secrets()

    db_settings = MultiDatabaseSettings.from_settings(settings)
    repos = await initialize_databases(db_settings)

    registry = get_agent_registry()
    app.state.settings = settings
    app.state.agent_registry = registry
    app.state.session_manager = get_session_manager()
    app.state.telemetry_recorder = get_telemetry_recorder()
    app.state.db_repos = repos

    logger.info(
        "application_started",
        app_name=settings.app_name,
        environment=settings.app_env,
        registered_agents=registry.list_ids(),
        telemetry_db=repos["telemetry"].enabled,
    )


async def on_shutdown(app: FastAPI) -> None:
    await shutdown_databases()
    logger.info("application_shutdown", app_name=getattr(app.state, "settings", None))
