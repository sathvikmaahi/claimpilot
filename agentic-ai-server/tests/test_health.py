"""Health endpoint tests."""


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "agentic-ai-server"


def test_readiness(client):
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["agents_registered"] >= 3
    assert "echo" in body["agent_ids"]
    assert "databases" in body
