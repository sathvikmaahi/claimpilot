"""CLI entry point for agent scaffolding."""

from __future__ import annotations

import argparse
import sys

from tools.scaffold.generator import PROJECT_ROOT, scaffold_agent
from tools.scaffold.templates import AgentTemplate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scaffold a new agent or multi-agent system for agentic-ai-server.",
    )
    parser.add_argument("agent_id", help="Unique slug (e.g. benefits_assistant)")
    parser.add_argument("--name", required=True, help="Human-readable name")
    parser.add_argument("--description", required=True, help="Short description")
    parser.add_argument(
        "--template",
        choices=[t.value for t in AgentTemplate],
        default=AgentTemplate.SIMPLE.value,
        help="Scaffold template type",
    )
    parser.add_argument("--model", default="gemini-2.0-flash", help="Default ADK model")
    parser.add_argument(
        "--conversational",
        action="store_true",
        help="Enable session-aware mode (chat-system only)",
    )
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="Skip registry.yaml update",
    )

    args = parser.parse_args()
    template = AgentTemplate(args.template)

    if args.conversational and template != AgentTemplate.CHAT_SYSTEM:
        print("Warning: --conversational only applies to chat-system templates", file=sys.stderr)

    try:
        paths = scaffold_agent(
            agent_id=args.agent_id,
            name=args.name,
            description=args.description,
            template=template,
            model=args.model,
            conversational=args.conversational,
            register=not args.no_register,
        )
    except (ValueError, FileExistsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Scaffolded agent '{args.agent_id}' ({template.value}):")
    for path in paths:
        print(f"  - {path.relative_to(PROJECT_ROOT)}")
    print("\nNext steps:")
    print(f"  1. Review agents/{args.agent_id}/")
    print("  2. uv run pytest tests/agents/ -q")
    print(f"  3. uv run agentic-ai-server  →  POST /agents/{args.agent_id}/run")


if __name__ == "__main__":
    main()
