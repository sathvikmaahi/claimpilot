"""Rolling conversation summarization pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.conversation.models import ConversationTurn, SessionSummary, utc_now
from core.conversation.policy import SummarizationPolicy


class Summarizer(ABC):
    @abstractmethod
    async def update_summary(
        self,
        *,
        current: SessionSummary,
        new_turns: list[ConversationTurn],
        policy: SummarizationPolicy,
    ) -> SessionSummary:
        """Produce an updated rolling summary from new turns."""


class RollingSummarizer(Summarizer):
    """Deterministic rolling summarizer suitable for tests and baseline production use."""

    async def update_summary(
        self,
        *,
        current: SessionSummary,
        new_turns: list[ConversationTurn],
        policy: SummarizationPolicy,
    ) -> SessionSummary:
        if not new_turns:
            return current

        lines: list[str] = []
        if current.text.strip():
            lines.append(current.text.strip())

        for turn in new_turns:
            prefix = turn.role.value.capitalize()
            lines.append(f"{prefix}: {turn.content.strip()}")

        merged = "\n".join(lines)
        if len(merged) > policy.max_summary_chars:
            merged = merged[-policy.max_summary_chars :]
            merged = f"[...truncated...]\n{merged}"

        return SessionSummary(
            session_id=current.session_id,
            text=merged,
            turn_count=current.turn_count + len(new_turns),
            updated_at=utc_now(),
        )


class SummarizationPipeline:
    """Updates rolling summaries at controlled intervals."""

    def __init__(self, summarizer: Summarizer | None = None) -> None:
        self._summarizer = summarizer or RollingSummarizer()

    def should_summarize(self, turn_count: int, policy: SummarizationPolicy) -> bool:
        if turn_count == 0:
            return False
        # Summarize after every N complete user+assistant pairs (2 turns each)
        pairs = turn_count // 2
        return pairs > 0 and pairs % policy.summarize_every_n_turns == 0

    async def maybe_update(
        self,
        *,
        summary: SessionSummary,
        all_turns: list[ConversationTurn],
        policy: SummarizationPolicy,
        force: bool = False,
    ) -> SessionSummary:
        turn_count = len(all_turns)
        if not force and not self.should_summarize(turn_count, policy):
            return summary.model_copy(update={"turn_count": turn_count})

        # Only summarize turns not yet reflected in summary turn_count
        new_turns = all_turns[summary.turn_count :]
        if not new_turns and not force:
            return summary

        if force and not new_turns:
            new_turns = all_turns[-policy.recent_turns_window * 2 :] if all_turns else []

        return await self._summarizer.update_summary(
            current=summary,
            new_turns=new_turns,
            policy=policy,
        )
