"""Build agent-facing context from summary artifacts — not full transcript replay."""

from __future__ import annotations

from core.conversation.models import (
    ConversationSession,
    ConversationTurn,
    PreparedConversationContext,
    SessionSummary,
    TurnRole,
)
from core.conversation.policy import SummarizationPolicy


def _format_turns(turns: list[ConversationTurn]) -> str:
    if not turns:
        return "(none)"
    return "\n".join(f"{turn.role.value}: {turn.content}" for turn in turns)


def _format_memory(snippets: list[str]) -> str:
    if not snippets:
        return "(none)"
    return "\n".join(f"- {snippet}" for snippet in snippets)


def build_prepared_context(
    *,
    session: ConversationSession,
    summary: SessionSummary,
    all_turns: list[ConversationTurn],
    memory_snippets: list[str],
    policy: SummarizationPolicy,
) -> PreparedConversationContext:
    recent = all_turns[-policy.recent_turns_window * 2 :] if policy.recent_turns_window else []
    return PreparedConversationContext(
        session=session,
        summary=summary,
        recent_turns=recent,
        memory_snippets=memory_snippets,
    )


def build_agent_message(
    user_message: str,
    context: PreparedConversationContext,
    *,
    include_transcript: bool = False,
    full_turns: list[ConversationTurn] | None = None,
) -> str:
    """Compose the message sent to the agent using summary-first context."""
    sections = [
        "[Conversation Summary]",
        context.summary.text or "(no prior summary)",
        "",
        "[Recent Messages]",
        _format_turns(context.recent_turns),
        "",
        "[Relevant Long-term Memory]",
        _format_memory(context.memory_snippets),
    ]

    if include_transcript and full_turns:
        sections.extend(["", "[Full Transcript — explicit request]", _format_turns(full_turns)])

    sections.extend(["", "[Current User Message]", user_message])
    return "\n".join(sections)


def split_user_and_assistant_turns(
    user_message: str,
    assistant_message: str,
    *,
    start_index: int,
) -> list[ConversationTurn]:
    return [
        ConversationTurn(turn_index=start_index, role=TurnRole.USER, content=user_message),
        ConversationTurn(
            turn_index=start_index + 1,
            role=TurnRole.ASSISTANT,
            content=assistant_message,
        ),
    ]
