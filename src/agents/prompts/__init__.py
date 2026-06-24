"""Agent instruction prompts, kept separate from agent code.

Edit the .md files in this folder to change an agent's behavior — no need to
touch agent.py. Templates use placeholder tokens (e.g. {goals_text}) that the
agent builder substitutes via str.replace at call time. (We use replace, not
str.format, so literal JSON braces in the prompt are left untouched.)
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Return the raw instruction template for the named agent.

    e.g. load_prompt("narrative_extractor") -> contents of narrative_extractor.md
    """
    return (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
