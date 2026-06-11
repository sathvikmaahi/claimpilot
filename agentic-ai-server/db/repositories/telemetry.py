"""ORM repositories for telemetry and business event persistence."""

from __future__ import annotations

import structlog

from db.config import DatabaseRole
from db.engines import get_engine, get_session
from db.models.telemetry import AgentExecutionEvent, BusinessEvent
from telemetry.events import BusinessEventRecord, ExecutionEventRecord

logger = structlog.get_logger(__name__)


class TelemetryRepository:
    """Persists normalized execution metadata to the telemetry database."""

    def __init__(self, role: DatabaseRole = DatabaseRole.TELEMETRY) -> None:
        self._role = role

    @property
    def enabled(self) -> bool:
        return get_engine(self._role) is not None

    async def ensure_schema(self) -> None:
        engine = get_engine(self._role)
        if engine is None:
            return
        from db.base import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def record_execution(self, event: ExecutionEventRecord) -> str | None:
        if not self.enabled:
            return None

        row = AgentExecutionEvent(
            trace_id=event.trace_id,
            span_id=event.span_id,
            request_id=event.request_id,
            agent_id=event.agent_id,
            agent_name=event.agent_name,
            session_id=event.session_id,
            user_id=event.user_id,
            status=event.status,
            latency_ms=event.latency_ms,
            tool_invocations=event.tool_invocations,
            token_input=event.token_input,
            token_output=event.token_output,
            error_message=event.error_message,
            event_metadata=event.metadata,
        )
        async with get_session(self._role) as session:
            session.add(row)
            await session.flush()
            return row.id

    async def record_business_event(self, event: BusinessEventRecord) -> str | None:
        if not self.enabled:
            return None

        row = BusinessEvent(
            trace_id=event.trace_id,
            event_type=event.event_type,
            agent_id=event.agent_id,
            session_id=event.session_id,
            user_id=event.user_id,
            payload=event.payload,
        )
        async with get_session(self._role) as session:
            session.add(row)
            await session.flush()
            return row.id


class AnalyticsRepository:
    """Optional analytics database for reporting-oriented writes."""

    def __init__(self) -> None:
        self._telemetry = TelemetryRepository(role=DatabaseRole.ANALYTICS)

    @property
    def enabled(self) -> bool:
        return self._telemetry.enabled

    async def ensure_schema(self) -> None:
        await self._telemetry.ensure_schema()

    async def record_business_event(self, event: BusinessEventRecord) -> str | None:
        return await self._telemetry.record_business_event(event)
