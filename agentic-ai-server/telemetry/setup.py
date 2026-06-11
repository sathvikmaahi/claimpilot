"""Unified OpenTelemetry setup with ADK integration."""

from __future__ import annotations

import os

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from core.config import Settings
from telemetry.redaction import RedactionPolicy, apply_adk_privacy_env

logger = structlog.get_logger(__name__)
_configured = False


def configure_observability(settings: Settings) -> None:
    """Configure ADK + framework OpenTelemetry providers and privacy defaults."""
    global _configured
    if _configured:
        return

    policy = RedactionPolicy.from_settings(settings)
    apply_adk_privacy_env(policy)

    if not settings.otel_enabled:
        _configured = True
        return

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.namespace": settings.app_name,
            "deployment.environment": settings.app_env,
        }
    )

    hooks = []
    if settings.trace_to_cloud:
        try:
            from google.adk.telemetry.google_cloud import get_gcp_exporters

            hooks.append(
                get_gcp_exporters(
                    enable_cloud_tracing=True,
                    enable_cloud_metrics=settings.otel_metrics_enabled,
                    enable_cloud_logging=settings.otel_logs_enabled,
                )
            )
            logger.info("adk_gcp_exporters_configured")
        except Exception:
            logger.exception("adk_gcp_exporter_setup_failed")

    # Console fallback for local development
    from google.adk.telemetry.setup import OTelHooks, maybe_set_otel_providers

    if settings.app_env == "development" and not settings.trace_to_cloud:
        hooks.append(OTelHooks(span_processors=[BatchSpanProcessor(ConsoleSpanExporter())]))

    maybe_set_otel_providers(otel_hooks_to_setup=hooks, otel_resource=resource)

    # Honor OTLP env vars (OTEL_EXPORTER_OTLP_ENDPOINT) via ADK setup
    os.environ.setdefault("OTEL_SERVICE_NAME", settings.otel_service_name)

    _configured = True
    logger.info(
        "observability_configured",
        otel_enabled=True,
        trace_to_cloud=settings.trace_to_cloud,
        capture_message_content=policy.capture_message_content,
    )


def instrument_fastapi(app: object, settings: Settings) -> None:
    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def current_trace_ids() -> tuple[str | None, str | None]:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx or not ctx.is_valid:
        return None, None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")
