"""Privacy-conscious redaction for logs, spans, and persisted telemetry."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


class RedactionPolicy(BaseModel):
    """Controls what sensitive content is captured in telemetry."""

    capture_message_content: bool = False
    capture_span_content: bool = False
    max_message_preview_chars: int = Field(default=0, ge=0, le=500)
    redact_field_names: list[str] = Field(
        default_factory=lambda: [
            "password",
            "api_key",
            "token",
            "secret",
            "authorization",
            "ssn",
            "credit_card",
        ]
    )

    @classmethod
    def privacy_default(cls) -> RedactionPolicy:
        return cls()

    @classmethod
    def from_settings(cls, settings: object) -> RedactionPolicy:
        from core.config import Settings

        if not isinstance(settings, Settings):
            return cls.privacy_default()
        return cls(
            capture_message_content=settings.telemetry_capture_message_content,
            capture_span_content=settings.telemetry_capture_span_content,
            max_message_preview_chars=settings.telemetry_message_preview_chars,
        )


_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_PATTERN = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")


def _mask_patterns(text: str) -> str:
    text = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    return _PHONE_PATTERN.sub("[REDACTED_PHONE]", text)


def redact_text(text: str, policy: RedactionPolicy) -> str:
    if policy.capture_message_content:
        return _mask_patterns(text)
    if policy.max_message_preview_chars > 0:
        preview = text[: policy.max_message_preview_chars]
        masked = _mask_patterns(preview)
        return f"{masked}…" if len(text) > len(preview) else masked
    return "[REDACTED]"


def redact_dict(data: dict[str, Any], policy: RedactionPolicy) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    sensitive = {name.lower() for name in policy.redact_field_names}
    for key, value in data.items():
        if key.lower() in sensitive:
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_dict(value, policy)
        elif isinstance(value, str):
            redacted[key] = value
        else:
            redacted[key] = value
    return redacted


def apply_adk_privacy_env(policy: RedactionPolicy) -> None:
    """Set ADK environment defaults for privacy-conscious span content."""
    import os

    if not policy.capture_span_content:
        os.environ.setdefault("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "false")
        os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false")
