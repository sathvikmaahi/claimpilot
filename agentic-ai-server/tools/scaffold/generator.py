"""Scaffold a new agent or agent system."""

from __future__ import annotations

import re
from pathlib import Path

from tools.scaffold.registry import append_registry_entry
from tools.scaffold.templates import (
    AgentTemplate,
    ScaffoldOptions,
    render_agent_py,
    render_init,
    render_registry_entry,
    render_simple_handler,
    render_system_handler,
    render_system_manifest,
    render_test,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = PROJECT_ROOT / "agents"
TESTS_DIR = PROJECT_ROOT / "tests" / "agents"
REGISTRY_PATH = AGENTS_DIR / "registry.yaml"

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_agent_id(agent_id: str) -> None:
    if not _IDENTIFIER.match(agent_id):
        raise ValueError(
            f"Invalid agent id '{agent_id}': use lowercase letters, digits, underscores; "
            "must start with a letter."
        )


def scaffold_agent(
    *,
    agent_id: str,
    name: str,
    description: str,
    template: AgentTemplate,
    model: str = "gemini-2.0-flash",
    conversational: bool = False,
    register: bool = True,
) -> list[Path]:
    """Create agent files, test stub, and registry entry."""
    validate_agent_id(agent_id)
    opts = ScaffoldOptions(
        agent_id=agent_id,
        name=name,
        description=description,
        template=template,
        model=model,
        conversational=conversational,
    )

    agent_dir = AGENTS_DIR / agent_id
    if agent_dir.exists():
        raise FileExistsError(f"Agent directory already exists: {agent_dir}")

    created: list[Path] = []
    agent_dir.mkdir(parents=True)

    files: dict[str, str] = {
        "__init__.py": render_init(),
    }

    if template == AgentTemplate.SIMPLE:
        files["agent.py"] = render_agent_py(opts)
        files["handler.py"] = render_simple_handler(opts)
    else:
        files["manifest.yaml"] = render_system_manifest(opts)
        files["handler.py"] = render_system_handler(opts)

    for filename, content in files.items():
        path = agent_dir / filename
        path.write_text(content, encoding="utf-8")
        created.append(path)

    TESTS_DIR.mkdir(parents=True, exist_ok=True)
    test_path = TESTS_DIR / f"test_{agent_id}.py"
    test_path.write_text(render_test(opts), encoding="utf-8")
    created.append(test_path)

    if register:
        entry = render_registry_entry(opts)
        append_registry_entry(REGISTRY_PATH, entry)
        created.append(REGISTRY_PATH)

    return created
