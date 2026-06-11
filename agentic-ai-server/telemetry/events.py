"""Normalized telemetry event schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExecutionEventRecord(BaseModel):
    agent_id: str
    agent_name: str = ""
    session_id: str | None = None
    user_id: str = "anonymous"
    status: str
    latency_ms: float
    trace_id: str | None = None
    span_id: str | None = None
    request_id: str | None = None
    tool_invocations: list[dict[str, Any]] = Field(default_factory=list)
    token_input: int | None = None
    token_output: int | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BusinessEventRecord(BaseModel):
    event_type: str
    agent_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    trace_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
