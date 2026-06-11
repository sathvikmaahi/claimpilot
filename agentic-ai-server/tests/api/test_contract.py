"""API contract tests for public endpoints."""

import pytest


@pytest.mark.api
def test_list_agents_contract(client):
    response = client.get("/agents")
    assert response.status_code == 200
    body = response.json()
    assert "agents" in body
    assert isinstance(body["agents"], list)
    if body["agents"]:
        agent = body["agents"][0]
        assert {"id", "name", "description"} <= agent.keys()


@pytest.mark.api
def test_get_agent_contract(client):
    response = client.get("/agents/echo")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "echo"
    assert "name" in body
    assert "description" in body


@pytest.mark.api
def test_run_agent_request_validation(client):
    response = client.post("/agents/echo/run", json={})
    assert response.status_code == 422


@pytest.mark.api
def test_run_agent_response_shape(client):
    response = client.post("/agents/chat_assistant/run", json={"message": "hi"})
    assert response.status_code == 200
    body = response.json()
    assert {"agent_id", "session_id", "message", "events", "metadata"} <= body.keys()


@pytest.mark.api
def test_unknown_agent_returns_404(client):
    response = client.get("/agents/does_not_exist")
    assert response.status_code == 404


@pytest.mark.api
@pytest.mark.session
def test_create_session_contract(client):
    response = client.post(
        "/agents/chat_assistant/sessions",
        json={"user_id": "contract-test"},
    )
    assert response.status_code == 200
    body = response.json()
    assert {"session_id", "status", "summary", "turn_count"} <= body.keys()
