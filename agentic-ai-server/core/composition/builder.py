"""Build orchestration graphs from declarative manifests."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from google.adk import Agent
from google.adk.sessions.base_session_service import BaseSessionService

from core.composition.context import OrchestrationContext, SubAgentResult, SubAgentStatus
from core.composition.manifest import AgentSystemManifest, GraphStepManifest, NodeManifest
from core.composition.nodes import ADKSubAgent, FunctionSubAgent, SubAgent, SubAgentCallable
from core.composition.primitives import (
    NodeStep,
    OrchestrationStep,
    ParallelFlow,
    RetryLoopFlow,
    RouterFlow,
    SequentialFlow,
)
from core.composition.roles import AgentRole
from core.config import Settings


def _default_handler(
    node_id: str, role: AgentRole, manifest: NodeManifest
) -> SubAgentCallable:
    async def handler(context: OrchestrationContext) -> SubAgentResult:
        return SubAgentResult(
            node_id=node_id,
            role=role,
            status=SubAgentStatus.SUCCESS,
            message=f"[{node_id}] processed: {context.user_message}",
            structured={manifest.output_key or "route": "default"},
        )

    return handler


def build_sub_agent(
    *,
    node_id: str,
    manifest: NodeManifest,
    settings: Settings,
    session_service: BaseSessionService,
    handler_override: SubAgent | None = None,
) -> SubAgent:
    if handler_override is not None:
        return handler_override

    if manifest.instruction:
        model = manifest.model or "gemini-2.0-flash"
        agent = Agent(
            name=node_id,
            model=model,
            instruction=manifest.instruction,
        )
        return ADKSubAgent(
            node_id=node_id,
            role=manifest.role,
            agent=agent,
            session_service=session_service,
            app_name=settings.app_name,
            input_template=manifest.input_template,
        )

    return FunctionSubAgent(
        node_id=node_id,
        role=manifest.role,
        handler=_default_handler(node_id, manifest.role, manifest),
    )


def build_nodes(
    manifest: AgentSystemManifest,
    settings: Settings,
    session_service: BaseSessionService,
    node_overrides: Mapping[str, SubAgent] | None = None,
) -> dict[str, SubAgent]:
    overrides = node_overrides or {}
    nodes: dict[str, SubAgent] = {}
    for node_id, node_manifest in manifest.nodes.items():
        nodes[node_id] = build_sub_agent(
            node_id=node_id,
            manifest=node_manifest,
            settings=settings,
            session_service=session_service,
            handler_override=overrides.get(node_id),
        )
    return nodes


def _build_step(
    step_manifest: GraphStepManifest | str,
    nodes: dict[str, SubAgent],
) -> OrchestrationStep:
    if isinstance(step_manifest, str):
        return NodeStep(nodes[step_manifest])

    if step_manifest.type == "node":
        if not step_manifest.node:
            raise ValueError("Node step requires 'node'")
        return NodeStep(nodes[step_manifest.node])

    if step_manifest.type == "sequential":
        inner_steps = [_build_step(step, nodes) for step in step_manifest.steps]
        return SequentialFlow(inner_steps)

    if step_manifest.type == "parallel":
        inner_steps = [_build_step(step, nodes) for step in step_manifest.steps]
        return ParallelFlow(inner_steps)

    if step_manifest.type == "router":
        if not step_manifest.source:
            raise ValueError("Router step requires 'source'")
        return RouterFlow(
            source_node=step_manifest.source,
            route_field=step_manifest.field,
            routes=step_manifest.routes,
            nodes=nodes,
            default_route=step_manifest.default,
        )

    if step_manifest.type == "retry":
        if step_manifest.inner is None:
            raise ValueError("Retry step requires 'inner'")
        inner = _build_step(step_manifest.inner, nodes)
        return RetryLoopFlow(inner, max_attempts=step_manifest.max_attempts)

    raise ValueError(f"Unsupported graph step type: {step_manifest.type}")


def build_pipeline(
    manifest: AgentSystemManifest,
    settings: Settings,
    session_service: BaseSessionService,
    node_overrides: Mapping[str, SubAgent] | None = None,
) -> OrchestrationStep:
    nodes = build_nodes(manifest, settings, session_service, node_overrides)
    steps = [_build_step(step, nodes) for step in manifest.graph]
    return SequentialFlow(steps)


def load_agent_system_manifest(path: str | Path) -> AgentSystemManifest:
    return AgentSystemManifest.from_yaml(Path(path))
