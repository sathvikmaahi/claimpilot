"""Registry-driven agent discovery and lookup."""

from __future__ import annotations

from core.agents.contract import AgentContract
from core.exceptions import AgentNotFoundError


class AgentRegistry:
    """In-memory registry populated at startup from configuration."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentContract] = {}

    def register(self, agent: AgentContract) -> None:
        if agent.agent_id in self._agents:
            raise ValueError(f"Agent already registered: {agent.agent_id}")
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> AgentContract:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise AgentNotFoundError(
                f"Agent '{agent_id}' is not registered",
                details={"agent_id": agent_id, "available": self.list_ids()},
            )
        return agent

    def list_agents(self) -> list[AgentContract]:
        return list(self._agents.values())

    def list_ids(self) -> list[str]:
        return sorted(self._agents.keys())

    def __len__(self) -> int:
        return len(self._agents)
