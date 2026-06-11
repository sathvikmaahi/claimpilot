"""Tests for orchestration primitives."""

import pytest

from core.composition.context import SubAgentResult, SubAgentStatus
from core.composition.nodes import FunctionSubAgent
from core.composition.primitives import (
    NodeStep,
    ParallelFlow,
    RetryLoopFlow,
    RouterFlow,
    SequentialFlow,
)
from core.composition.roles import AgentRole
from tests.composition.fixtures import make_context, result


@pytest.mark.asyncio
async def test_sequential_flow_runs_in_order():
    calls: list[str] = []

    async def step_a(_ctx):
        calls.append("a")
        return result("a", message="a")

    async def step_b(_ctx):
        calls.append("b")
        return result("b", message="b")

    flow = SequentialFlow(
        [
            NodeStep(FunctionSubAgent(node_id="a", role=AgentRole.TASK, handler=step_a)),
            NodeStep(FunctionSubAgent(node_id="b", role=AgentRole.TASK, handler=step_b)),
        ]
    )
    ctx = await flow.run(make_context())
    assert calls == ["a", "b"]
    assert ctx.trace == ["a", "b"]
    assert ctx.latest_message() == "b"


@pytest.mark.asyncio
async def test_parallel_flow_merges_outputs():
    async def slow_a(_ctx):
        return result("a", message="parallel-a")

    async def slow_b(_ctx):
        return result("b", message="parallel-b")

    flow = ParallelFlow(
        [
            NodeStep(FunctionSubAgent(node_id="a", role=AgentRole.TASK, handler=slow_a)),
            NodeStep(FunctionSubAgent(node_id="b", role=AgentRole.TASK, handler=slow_b)),
        ]
    )
    ctx = await flow.run(make_context())
    assert set(ctx.outputs.keys()) == {"a", "b"}


@pytest.mark.asyncio
async def test_router_selects_target():
    async def orchestrator(_ctx):
        return result("orchestrator", role=AgentRole.ORCHESTRATOR, structured={"route": "task"})

    async def chat(_ctx):
        return result("chat", role=AgentRole.CONVERSATIONAL, message="chat-response")

    async def task(_ctx):
        return result("task", role=AgentRole.TASK, message="task-response")

    nodes = {
        "chat": FunctionSubAgent(node_id="chat", role=AgentRole.CONVERSATIONAL, handler=chat),
        "task": FunctionSubAgent(node_id="task", role=AgentRole.TASK, handler=task),
    }

    flow = SequentialFlow(
        [
            NodeStep(
                FunctionSubAgent(
                    node_id="orchestrator", role=AgentRole.ORCHESTRATOR, handler=orchestrator
                )
            ),
            RouterFlow(
                source_node="orchestrator",
                route_field="route",
                routes={"chat": "chat", "task": "task"},
                nodes=nodes,
            ),
        ]
    )
    ctx = await flow.run(make_context("process my claim"))
    assert ctx.outputs["task"].message == "task-response"
    assert ctx.shared["route"]["selected"] == "task"


@pytest.mark.asyncio
async def test_retry_loop_retries_until_success():
    attempts = {"count": 0}

    async def flaky(_ctx):
        attempts["count"] += 1
        if attempts["count"] < 2:
            return SubAgentResult(
                node_id="validate",
                role=AgentRole.TASK,
                status=SubAgentStatus.FAILURE,
                error="not yet",
            )
        return result("validate", message="validated")

    flow = RetryLoopFlow(
        NodeStep(FunctionSubAgent(node_id="validate", role=AgentRole.TASK, handler=flaky)),
        max_attempts=3,
    )
    ctx = await flow.run(make_context("claim-123"))
    assert attempts["count"] == 2
    assert ctx.outputs["validate"].succeeded
