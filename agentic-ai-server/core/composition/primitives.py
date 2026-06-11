"""Reusable orchestration primitives for agent system composition."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable

from core.composition.context import OrchestrationContext
from core.composition.nodes import SubAgent


class OrchestrationStep(ABC):
    """A composable unit in an agent-system execution graph."""

    @abstractmethod
    async def run(self, context: OrchestrationContext) -> OrchestrationContext:
        """Execute this step and return the updated context."""


class NodeStep(OrchestrationStep):
    """Orchestration step that executes a single sub-agent node."""

    def __init__(self, node: SubAgent) -> None:
        self.node = node

    async def run(self, context: OrchestrationContext) -> OrchestrationContext:
        result = await self.node.execute(context)
        context.record(self.node.node_id, result)
        if result.failed:
            context.shared["last_failure"] = result.model_dump()
        return context


class SequentialFlow(OrchestrationStep):
    """Run steps one after another, stopping early on failure."""

    def __init__(self, steps: list[OrchestrationStep], *, stop_on_failure: bool = True) -> None:
        self.steps = steps
        self.stop_on_failure = stop_on_failure

    async def run(self, context: OrchestrationContext) -> OrchestrationContext:
        for step in self.steps:
            context = await step.run(context)
            if self.stop_on_failure and context.shared.get("last_failure"):
                break
        return context


class ParallelFlow(OrchestrationStep):
    """Run steps concurrently and merge their outputs."""

    def __init__(self, steps: list[OrchestrationStep]) -> None:
        self.steps = steps

    async def run(self, context: OrchestrationContext) -> OrchestrationContext:
        branches = [step.run(context.fork()) for step in self.steps]
        results = await asyncio.gather(*branches)
        for branch_context in results:
            context.merge_branch(branch_context)
        return context


class RouterFlow(OrchestrationStep):
    """Route execution to one downstream node based on structured output."""

    def __init__(
        self,
        *,
        source_node: str,
        route_field: str,
        routes: dict[str, str],
        nodes: dict[str, SubAgent],
        default_route: str | None = None,
    ) -> None:
        self.source_node = source_node
        self.route_field = route_field
        self.routes = routes
        self.nodes = nodes
        self.default_route = default_route or routes.get("default", next(iter(routes.values())))

    def _resolve_target(self, context: OrchestrationContext) -> str:
        route_key = context.get_structured(self.source_node, self.route_field, "default")
        return self.routes.get(str(route_key), self.default_route)

    async def run(self, context: OrchestrationContext) -> OrchestrationContext:
        target_id = self._resolve_target(context)
        node = self.nodes[target_id]
        step = NodeStep(node)
        routed_context = await step.run(context)
        routed_context.shared["route"] = {
            "source": self.source_node,
            "field": self.route_field,
            "selected": target_id,
        }
        return routed_context


class RetryLoopFlow(OrchestrationStep):
    """Retry a step until success or max attempts, with optional predicate."""

    def __init__(
        self,
        step: OrchestrationStep,
        *,
        max_attempts: int = 3,
        until: Callable[[OrchestrationContext], bool] | None = None,
    ) -> None:
        self.step = step
        self.max_attempts = max_attempts
        self.until = until or (lambda ctx: not ctx.shared.get("last_failure"))

    async def run(self, context: OrchestrationContext) -> OrchestrationContext:
        for attempt in range(1, self.max_attempts + 1):
            context.shared.pop("last_failure", None)
            context = await self.step.run(context)
            context.shared["retry_attempt"] = attempt
            if self.until(context):
                return context
        context.shared["retry_exhausted"] = True
        return context


class ConditionalFlow(OrchestrationStep):
    """Run a step only when a predicate matches."""

    def __init__(
        self,
        step: OrchestrationStep,
        predicate: Callable[[OrchestrationContext], bool],
    ) -> None:
        self.step = step
        self.predicate = predicate

    async def run(self, context: OrchestrationContext) -> OrchestrationContext:
        if self.predicate(context):
            return await self.step.run(context)
        return context
