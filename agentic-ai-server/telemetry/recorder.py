"""Telemetry persistence and span correlation."""

from __future__ import annotations

import time
from contextlib import AbstractContextManager
from typing import Any

import structlog

from db.repositories.telemetry import AnalyticsRepository, TelemetryRepository
from telemetry.events import BusinessEventRecord, ExecutionEventRecord
from telemetry.redaction import RedactionPolicy, redact_dict, redact_text
from telemetry.setup import current_trace_ids, get_tracer

logger = structlog.get_logger(__name__)


def extract_token_usage(events: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    input_tokens = 0
    output_tokens = 0
    found = False
    for event in events:
        usage = event.get("usage_metadata") or {}
        if usage:
            found = True
            input_tokens += int(usage.get("prompt_token_count") or usage.get("input_tokens") or 0)
            output_tokens += int(
                usage.get("candidates_token_count") or usage.get("output_tokens") or 0
            )
    if not found:
        return None, None
    return input_tokens or None, output_tokens or None


def extract_tool_invocations(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for event in events:
        actions = event.get("actions") or {}
        if isinstance(actions, dict):
            for key, value in actions.items():
                if "tool" in key.lower():
                    tools.append({"action": key, "detail": str(value)[:200]})
    return tools


class TelemetryRecorder:
    """Writes normalized execution rows and emits correlated spans."""

    def __init__(
        self,
        *,
        telemetry_repo: TelemetryRepository,
        analytics_repo: AnalyticsRepository | None = None,
        policy: RedactionPolicy | None = None,
    ) -> None:
        self._telemetry = telemetry_repo
        self._analytics = analytics_repo or AnalyticsRepository()
        self._policy = policy or RedactionPolicy.privacy_default()
        self._tracer = get_tracer(__name__)

    async def record_execution(
        self,
        *,
        agent_id: str,
        agent_name: str,
        session_id: str | None,
        user_id: str,
        status: str,
        latency_ms: float,
        request_id: str | None = None,
        events: list[dict[str, Any]] | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        trace_id, span_id = current_trace_ids()
        token_in, token_out = extract_token_usage(events or [])
        tools = extract_tool_invocations(events or [])

        record = ExecutionEventRecord(
            trace_id=trace_id,
            span_id=span_id,
            request_id=request_id,
            agent_id=agent_id,
            agent_name=agent_name,
            session_id=session_id,
            user_id=user_id,
            status=status,
            latency_ms=latency_ms,
            tool_invocations=tools,
            token_input=token_in,
            token_output=token_out,
            error_message=redact_text(error_message, self._policy) if error_message else None,
            metadata=redact_dict(metadata or {}, self._policy),
        )

        event_id = await self._telemetry.record_execution(record)
        logger.info(
            "agent_execution_recorded",
            agent_id=agent_id,
            status=status,
            latency_ms=round(latency_ms, 2),
            trace_id=trace_id,
            telemetry_persisted=event_id is not None,
        )
        return event_id

    async def record_business_event(
        self,
        *,
        event_type: str,
        agent_id: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        trace_id, _ = current_trace_ids()
        record = BusinessEventRecord(
            event_type=event_type,
            agent_id=agent_id,
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            payload=redact_dict(payload or {}, self._policy),
        )
        await self._telemetry.record_business_event(record)
        if self._analytics.enabled:
            await self._analytics.record_business_event(record)

    def agent_execution_span(
        self, agent_id: str, session_id: str | None, user_id: str
    ) -> AbstractContextManager[object]:
        return self._tracer.start_as_current_span(
            "agent.execute",
            attributes={
                "agent.id": agent_id,
                "agent.session_id": session_id or "",
                "agent.user_id": user_id,
            },
        )


class ExecutionTimer:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000
