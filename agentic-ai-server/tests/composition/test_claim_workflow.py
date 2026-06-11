"""Integration tests for the workflow-oriented agent system."""

import pytest

from agents.claim_workflow.handler import create_agent_handler
from core.agents.contract import AgentRequest
from core.config import Settings
from db.session import create_session_service


@pytest.fixture
def workflow_handler():
    settings = Settings(google_api_key="test")
    session_service = create_session_service(settings)
    return create_agent_handler(
        agent_id="claim_workflow",
        settings=settings,
        session_service=session_service,
        config={"manifest": "agents/claim_workflow/manifest.yaml"},
    )


@pytest.mark.asyncio
async def test_claim_workflow_runs_full_pipeline(workflow_handler):
    response = await workflow_handler.run(AgentRequest(message="claim-abc-123"))
    trace = response.metadata["trace"]
    assert "intake" in trace
    assert "validate" in trace
    assert "clinical_reviewer" in trace
    assert "billing_reviewer" in trace
    assert "merge_results" in trace
    assert "summarize" in trace
    assert "approved" in response.message


@pytest.mark.asyncio
async def test_claim_workflow_parallel_reviewers(workflow_handler):
    response = await workflow_handler.run(AgentRequest(message="claim-xyz"))
    node_outputs = response.metadata["node_outputs"]
    assert node_outputs["clinical_reviewer"]["status"] == "success"
    assert node_outputs["billing_reviewer"]["status"] == "success"
