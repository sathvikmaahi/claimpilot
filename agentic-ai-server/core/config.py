"""Application settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for local development and Cloud Run deployment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "agentic-ai-server"
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = Field(default=8080, validation_alias="PORT")

    # CORS
    cors_origins: str = "*"

    # Google ADK / GenAI
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    google_genai_use_vertexai: bool = False
    google_api_key: str = ""

    # Persistence
    session_service_uri: str = ""
    conversation_database_url: str = ""
    memory_enabled: bool = True
    app_database_url: str = ""
    telemetry_database_url: str = ""
    analytics_database_url: str = ""

    # Telemetry & observability
    otel_enabled: bool = True
    otel_service_name: str = "agentic-ai-server"
    otel_metrics_enabled: bool = False
    otel_logs_enabled: bool = False
    trace_to_cloud: bool = False
    telemetry_capture_message_content: bool = False
    telemetry_capture_span_content: bool = False
    telemetry_message_preview_chars: int = 0

    # Agent registry
    agent_registry_path: str = "agents/registry.yaml"

    @field_validator("port", mode="before")
    @classmethod
    def parse_port(cls, value: object) -> object:
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
