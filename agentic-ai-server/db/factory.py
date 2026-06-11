"""Database initialization helpers."""

from __future__ import annotations

from db.config import MultiDatabaseSettings
from db.engines import initialize_engines, shutdown_engines
from db.repositories.telemetry import AnalyticsRepository, TelemetryRepository


async def initialize_databases(
    settings: MultiDatabaseSettings,
) -> dict[str, TelemetryRepository | AnalyticsRepository]:
    initialize_engines(settings)
    telemetry_repo = TelemetryRepository()
    analytics_repo = AnalyticsRepository()

    if telemetry_repo.enabled:
        await telemetry_repo.ensure_schema()
    if analytics_repo.enabled:
        await analytics_repo.ensure_schema()

    return {
        "telemetry": telemetry_repo,
        "analytics": analytics_repo,
    }


async def shutdown_databases() -> None:
    await shutdown_engines()
