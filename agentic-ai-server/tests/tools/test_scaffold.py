"""Tests for the agent scaffold generator."""


import pytest
import yaml

import tools.scaffold.generator as generator
from tools.scaffold.generator import scaffold_agent, validate_agent_id
from tools.scaffold.templates import AgentTemplate


@pytest.mark.unit
def test_validate_agent_id():
    validate_agent_id("my_agent")
    with pytest.raises(ValueError):
        validate_agent_id("My-Agent")


@pytest.mark.unit
def test_scaffold_simple_agent(tmp_path, monkeypatch):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    tests_dir = tmp_path / "tests" / "agents"
    registry = agents_dir / "registry.yaml"
    registry.write_text("agents: []\n", encoding="utf-8")

    monkeypatch.setattr(generator, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(generator, "TESTS_DIR", tests_dir)
    monkeypatch.setattr(generator, "REGISTRY_PATH", registry)

    paths = scaffold_agent(
        agent_id="demo_bot",
        name="Demo Bot",
        description="A demo agent.",
        template=AgentTemplate.SIMPLE,
    )
    assert (agents_dir / "demo_bot" / "handler.py").exists()
    assert (tests_dir / "test_demo_bot.py").exists()
    assert len(paths) >= 3

    data = yaml.safe_load(registry.read_text())
    assert any(a["id"] == "demo_bot" for a in data["agents"])
