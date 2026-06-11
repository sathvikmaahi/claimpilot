"""Pytest fixtures and automatic test markers."""

import pytest
from fastapi.testclient import TestClient

from app.factory import create_app
from core.config import Settings


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Assign markers based on test module path when not explicitly set."""
    for item in items:
        path = str(item.fspath)
        if item.get_closest_marker("unit"):
            continue
        if "/tests/composition/" in path or "orchestration" in path:
            item.add_marker(pytest.mark.orchestration)
        elif "/tests/conversation/" in path:
            item.add_marker(pytest.mark.session)
        elif "/tests/api/" in path:
            item.add_marker(pytest.mark.api)
        elif "/tests/smoke/" in path:
            item.add_marker(pytest.mark.smoke)
        elif "/tests/telemetry/" in path or "/tests/tools/" in path:
            item.add_marker(pytest.mark.unit)
        elif path.endswith("test_health.py") or path.endswith("test_registry.py"):
            item.add_marker(pytest.mark.unit)


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        app_env="development",
        agent_registry_path="agents/registry.yaml",
        google_api_key="test-key",
        otel_enabled=False,
    )


@pytest.fixture
def client(test_settings: Settings) -> TestClient:
    app = create_app(settings=test_settings)
    with TestClient(app) as test_client:
        yield test_client
