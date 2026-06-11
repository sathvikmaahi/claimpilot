"""Tests for conversation context building."""

from core.conversation.context_builder import build_agent_message, build_prepared_context
from core.conversation.models import ConversationSession, ConversationTurn, SessionSummary, TurnRole
from core.conversation.policy import SummarizationPolicy


def test_build_agent_message_uses_summary_not_full_transcript():
    session = ConversationSession(agent_id="chat", user_id="u1")
    summary = SessionSummary(
        session_id=session.session_id,
        text="User discussed claims.",
        turn_count=4,
    )
    all_turns = [
        ConversationTurn(
            turn_index=i,
            role=TurnRole.USER if i % 2 == 0 else TurnRole.ASSISTANT,
            content=f"t{i}",
        )
        for i in range(6)
    ]
    prepared = build_prepared_context(
        session=session,
        summary=summary,
        all_turns=all_turns,
        memory_snippets=["Prior claim filed"],
        policy=SummarizationPolicy(recent_turns_window=1),
    )
    message = build_agent_message("New question", prepared)
    assert "User discussed claims." in message
    assert "t5" in message  # recent window
    assert "t0" not in message  # older turns excluded
    assert "Prior claim filed" in message


def test_include_transcript_opt_in():
    session = ConversationSession(agent_id="chat", user_id="u1")
    summary = SessionSummary(session_id=session.session_id, text="Summary", turn_count=2)
    all_turns = [
        ConversationTurn(turn_index=0, role=TurnRole.USER, content="old"),
        ConversationTurn(turn_index=1, role=TurnRole.ASSISTANT, content="reply"),
    ]
    prepared = build_prepared_context(
        session=session,
        summary=summary,
        all_turns=all_turns,
        memory_snippets=[],
        policy=SummarizationPolicy(),
    )
    message = build_agent_message(
        "Hi",
        prepared,
        include_transcript=True,
        full_turns=all_turns,
    )
    assert "Full Transcript" in message
    assert "old" in message
