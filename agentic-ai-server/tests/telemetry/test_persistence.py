"""Tests for telemetry persistence."""

import pytest

from db.config import DatabaseConfig, MultiDatabaseSettings
from db.engines import initialize_engines
from db.repositories.telemetry import TelemetryRepository
from telemetry.events import ExecutionEventRecord
from telemetry.recorder import TelemetryRecorder
from telemetry.redaction import RedactionPolicy


@pytest.mark.asyncio
async def test_telemetry_repository_persists_execution(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'telemetry.db'}"
    settings = MultiDatabaseSettings(
        telemetry=DatabaseConfig(url=db_url, enabled=True),
    )
    initialize_engines(settings)
    repo = TelemetryRepository()
    await repo.ensure_schema()

    record = ExecutionEventRecord(
        agent_id="echo",
        agent_name="Echo",
        session_id="sess-1",
        user_id="user-1",
        status="success",
        latency_ms=42.5,
        tool_invocations=[{"action": "tool_call"}],
    )
    event_id = await repo.record_execution(record)
    assert event_id is not None

    from db.engines import shutdown_engines

    await shutdown_engines()


@pytest.mark.asyncio
async def test_telemetry_recorder_skips_when_db_unconfigured():
    from db.engines import shutdown_engines

    await shutdown_engines()
    recorder = TelemetryRecorder(
        telemetry_repo=TelemetryRepository(),
        policy=RedactionPolicy.privacy_default(),
    )
    result = await recorder.record_execution(
        agent_id="echo",
        agent_name="Echo",
        session_id=None,
        user_id="u1",
        status="success",
        latency_ms=10.0,
    )
    assert result is None
