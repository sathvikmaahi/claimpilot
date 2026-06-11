"""Smoke tests for application startup."""

import pytest
from fastapi.testclient import TestClient

from app.factory import create_app
from core.config import Settings


@pytest.mark.smoke
def test_app_factory_starts():
    settings = Settings(otel_enabled=False, google_api_key="test")
    app = create_app(settings=settings)
    with TestClient(app) as client:
        health = client.get("/health")
        ready = client.get("/ready")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json()["status"] in {"ready", "degraded"}
    assert ready.json()["agents_registered"] >= 1


@pytest.mark.smoke
def test_all_registered_agents_respond(client: TestClient):
    agents = client.get("/agents").json()["agents"]
    for agent in agents:
        response = client.post(
            f"/agents/{agent['id']}/run",
            json={"message": "smoke test"},
        )
        assert response.status_code in {200, 502}, agent["id"]
