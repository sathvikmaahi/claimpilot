"""Registry YAML updates for scaffolded agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def append_registry_entry(registry_path: Path, entry: dict[str, Any]) -> None:
    with registry_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    agents = data.setdefault("agents", [])
    existing_ids = {a.get("id") for a in agents if isinstance(a, dict)}
    if entry["id"] in existing_ids:
        raise ValueError(f"Agent '{entry['id']}' already exists in registry")

    agents.append(entry)

    header = (
        "# Top-level agents mounted automatically as REST endpoints.\n"
        "# Add a new agent by creating a handler module and listing it here.\n\n"
    )
    body = yaml.dump(data, default_flow_style=False, sort_keys=False)
    registry_path.write_text(header + body, encoding="utf-8")
