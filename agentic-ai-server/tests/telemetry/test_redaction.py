"""Tests for telemetry redaction policy."""

from telemetry.redaction import RedactionPolicy, redact_dict, redact_text


def test_redact_text_default():
    policy = RedactionPolicy.privacy_default()
    assert redact_text("secret message content", policy) == "[REDACTED]"


def test_redact_text_preview():
    policy = RedactionPolicy(max_message_preview_chars=10)
    result = redact_text("hello world message", policy)
    assert result.startswith("hello worl")
    assert result.endswith("…")


def test_redact_dict_sensitive_keys():
    policy = RedactionPolicy()
    result = redact_dict({"password": "abc123", "name": "Alice"}, policy)
    assert result["password"] == "[REDACTED]"
    assert result["name"] == "Alice"
