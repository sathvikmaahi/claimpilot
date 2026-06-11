"""Structured logging configuration."""

from __future__ import annotations

import logging
import sys

import structlog

from core.config import Settings
from telemetry.redaction import RedactionPolicy, redact_dict


def _redaction_processor(settings: Settings) -> structlog.types.Processor:
    policy = RedactionPolicy.from_settings(settings)

    def processor(
        _logger: object,
        _method: str,
        event_dict: structlog.types.EventDict,
    ) -> structlog.types.EventDict:
        return redact_dict(dict(event_dict), policy)

    return processor


def configure_logging(settings: Settings) -> None:
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _redaction_processor(settings),
    ]

    if settings.app_env == "development":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(level=log_level, stream=sys.stdout, format="%(message)s")
