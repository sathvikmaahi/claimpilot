"""ORM models for normalized telemetry persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from db.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class AgentExecutionEvent(Base):
    """Normalized row for agent execution metadata (queryable operational store)."""

    __tablename__ = "agent_execution_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)
    span_id: Mapped[str | None] = mapped_column(String(32))
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    agent_name: Mapped[str] = mapped_column(String(256), default="")
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True, default="anonymous")
    status: Mapped[str] = mapped_column(String(32), index=True)
    latency_ms: Mapped[float] = mapped_column(Float)
    tool_invocations: Mapped[list[Any] | None] = mapped_column(JsonType, default=list)
    token_input: Mapped[int | None] = mapped_column(Integer)
    token_output: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JsonType, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )


class BusinessEvent(Base):
    """Selected business events persisted for analytics and auditing."""

    __tablename__ = "business_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(128), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    user_id: Mapped[str | None] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
