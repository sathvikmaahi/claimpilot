"""Health and readiness endpoints for Cloud Run probes."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from db.config import DatabaseRole
from db.engines import check_database

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadinessResponse(BaseModel):
    status: str
    agents_registered: int
    agent_ids: list[str]
    databases: dict[str, str] = Field(default_factory=dict)


@router.get("/health", response_model=HealthResponse)
@router.get("/healthz", response_model=HealthResponse, include_in_schema=False)
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(status="ok", service=settings.app_name)


@router.get("/ready", response_model=ReadinessResponse)
@router.get("/readyz", response_model=ReadinessResponse, include_in_schema=False)
async def ready(request: Request) -> ReadinessResponse:
    registry = request.app.state.agent_registry
    db_status = {
        role.value: await check_database(role)
        for role in (DatabaseRole.APP, DatabaseRole.TELEMETRY, DatabaseRole.ANALYTICS)
    }
    overall = "ready" if all(v in {"ok", "skipped"} for v in db_status.values()) else "degraded"
    return ReadinessResponse(
        status=overall,
        agents_registered=len(registry),
        agent_ids=registry.list_ids(),
        databases=db_status,
    )
