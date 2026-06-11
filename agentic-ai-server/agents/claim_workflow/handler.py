"""Deterministic handlers demonstrating the workflow-oriented agent system pattern."""

from __future__ import annotations

from typing import Any

from google.adk.sessions.base_session_service import BaseSessionService

from core.composition.context import OrchestrationContext, SubAgentResult, SubAgentStatus
from core.composition.factory import create_agent_system_handler
from core.composition.handler import AgentSystemHandler
from core.composition.nodes import FunctionSubAgent
from core.composition.roles import AgentRole
from core.config import Settings


async def _intake_handler(context: OrchestrationContext) -> SubAgentResult:
    claim_id = context.user_message.strip().replace(" ", "-")[:24] or "claim-unknown"
    return SubAgentResult(
        node_id="intake",
        role=AgentRole.ORCHESTRATOR,
        status=SubAgentStatus.SUCCESS,
        message=f"Intake complete for claim '{claim_id}'.",
        structured={"claim_id": claim_id, "raw": context.user_message},
    )


async def _validate_handler(context: OrchestrationContext) -> SubAgentResult:
    claim_id = context.get_structured("intake", "claim_id", "")
    attempt = context.shared.get("retry_attempt", 1)
    valid = bool(claim_id) and claim_id != "claim-unknown" and attempt >= 1
    status = SubAgentStatus.SUCCESS if valid else SubAgentStatus.FAILURE
    return SubAgentResult(
        node_id="validate",
        role=AgentRole.TASK,
        status=status,
        message="Validation passed." if valid else "Validation failed: missing claim id.",
        structured={"valid": valid},
        error=None if valid else "invalid_claim",
    )


async def _clinical_handler(context: OrchestrationContext) -> SubAgentResult:
    claim_id = context.get_structured("intake", "claim_id", "unknown")
    return SubAgentResult(
        node_id="clinical_reviewer",
        role=AgentRole.TASK,
        status=SubAgentStatus.SUCCESS,
        message=f"Clinical review approved for {claim_id}.",
        structured={"clinical_status": "approved"},
    )


async def _billing_handler(context: OrchestrationContext) -> SubAgentResult:
    claim_id = context.get_structured("intake", "claim_id", "unknown")
    return SubAgentResult(
        node_id="billing_reviewer",
        role=AgentRole.TASK,
        status=SubAgentStatus.SUCCESS,
        message=f"Billing review approved for {claim_id}.",
        structured={"billing_status": "approved"},
    )


async def _merge_handler(context: OrchestrationContext) -> SubAgentResult:
    clinical = context.get_structured("clinical_reviewer", "clinical_status")
    billing = context.get_structured("billing_reviewer", "billing_status")
    decision = "approved" if clinical == "approved" and billing == "approved" else "review"
    return SubAgentResult(
        node_id="merge_results",
        role=AgentRole.TOOL_WRAPPER,
        status=SubAgentStatus.SUCCESS,
        message=f"Merged decision: {decision}.",
        structured={"decision": decision},
    )


async def _summarize_handler(context: OrchestrationContext) -> SubAgentResult:
    decision = context.get_structured("merge_results", "decision", "unknown")
    claim_id = context.get_structured("intake", "claim_id", "unknown")
    summary = f"Workflow complete for {claim_id} with decision '{decision}'."
    return SubAgentResult(
        node_id="summarize",
        role=AgentRole.MEMORY,
        status=SubAgentStatus.SUCCESS,
        message=summary,
        structured={"summary": summary},
    )


def _demo_node_overrides() -> dict[str, FunctionSubAgent]:
    return {
        "intake": FunctionSubAgent(
            node_id="intake", role=AgentRole.ORCHESTRATOR, handler=_intake_handler
        ),
        "validate": FunctionSubAgent(
            node_id="validate", role=AgentRole.TASK, handler=_validate_handler
        ),
        "clinical_reviewer": FunctionSubAgent(
            node_id="clinical_reviewer", role=AgentRole.TASK, handler=_clinical_handler
        ),
        "billing_reviewer": FunctionSubAgent(
            node_id="billing_reviewer", role=AgentRole.TASK, handler=_billing_handler
        ),
        "merge_results": FunctionSubAgent(
            node_id="merge_results", role=AgentRole.TOOL_WRAPPER, handler=_merge_handler
        ),
        "summarize": FunctionSubAgent(
            node_id="summarize", role=AgentRole.MEMORY, handler=_summarize_handler
        ),
    }


def create_agent_handler(
    *,
    agent_id: str,
    settings: Settings,
    session_service: BaseSessionService,
    config: dict[str, Any],
) -> AgentSystemHandler:
    """Register the claim workflow as a declarative multi-agent system."""
    overrides = _demo_node_overrides()
    return create_agent_system_handler(
        agent_id=agent_id,
        settings=settings,
        session_service=session_service,
        config=config,
        node_overrides=overrides,
    )
