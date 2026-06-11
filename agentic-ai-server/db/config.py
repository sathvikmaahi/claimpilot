"""Multi-database configuration model."""

from __future__ import annotations

from enum import StrEnum
from typing import cast

from pydantic import BaseModel, Field


class DatabaseRole(StrEnum):
    APP = "app"
    TELEMETRY = "telemetry"
    ANALYTICS = "analytics"


class DatabaseConfig(BaseModel):
    """Connection settings for a single database role."""

    url: str = ""
    echo: bool = False
    pool_size: int = Field(default=5, ge=1, le=50)
    enabled: bool = True

    @property
    def is_configured(self) -> bool:
        return bool(self.url.strip())


class MultiDatabaseSettings(BaseModel):
    """Shared configuration for application, telemetry, and analytics databases."""

    app: DatabaseConfig = Field(default_factory=DatabaseConfig)
    telemetry: DatabaseConfig = Field(default_factory=DatabaseConfig)
    analytics: DatabaseConfig = Field(default_factory=DatabaseConfig)

    @classmethod
    def from_settings(cls, settings: object) -> MultiDatabaseSettings:
        from core.config import Settings

        if not isinstance(settings, Settings):
            raise TypeError("Expected Settings instance")
        return cls(
            app=DatabaseConfig(url=settings.app_database_url),
            telemetry=DatabaseConfig(url=settings.telemetry_database_url),
            analytics=DatabaseConfig(url=settings.analytics_database_url),
        )

    def get(self, role: DatabaseRole) -> DatabaseConfig:
        return cast(DatabaseConfig, getattr(self, role.value))
