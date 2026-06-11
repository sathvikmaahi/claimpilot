"""Per-agent summarization and conversation policies."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SummarizationPolicy(BaseModel):
    """Controls how aggressively a conversational agent compresses history."""

    summarize_every_n_turns: int = Field(
        default=4,
        ge=1,
        description="Update rolling summary after this many user+assistant turn pairs",
    )
    recent_turns_window: int = Field(
        default=2,
        ge=0,
        description="Number of recent raw turns to inject alongside the summary",
    )
    max_summary_chars: int = Field(
        default=2000,
        ge=100,
        description="Truncate rolling summary to this length",
    )
    persist_to_long_term_memory: bool = Field(
        default=True,
        description="Persist summary checkpoints to long-term memory",
    )
    checkpoint_on_close: bool = Field(
        default=True,
        description="Run memory checkpoint hooks when the session closes",
    )
    search_long_term_memory: bool = Field(
        default=True,
        description="Retrieve relevant long-term memories for each turn",
    )
    memory_search_limit: int = Field(default=3, ge=0, le=10)

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> SummarizationPolicy:
        if not config:
            return cls()
        return cls.model_validate(config)
