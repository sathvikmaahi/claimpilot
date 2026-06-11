"""OpenTelemetry tracing — delegates to unified observability setup."""

from telemetry.setup import configure_observability as configure_tracing
from telemetry.setup import current_trace_ids, get_tracer, instrument_fastapi

__all__ = ["configure_tracing", "current_trace_ids", "get_tracer", "instrument_fastapi"]
