"""Tests for rolling summarization pipeline."""

import pytest

from core.conversation.models import ConversationTurn, SessionSummary, TurnRole
from core.conversation.policy import SummarizationPolicy
from core.conversation.summarizer import SummarizationPipeline


@pytest.mark.asyncio
async def test_summarization_runs_at_interval():
    pipeline = SummarizationPipeline()
    policy = SummarizationPolicy(summarize_every_n_turns=2)
    summary = SessionSummary(session_id="s1", text="", turn_count=0)
    turns = [
        ConversationTurn(turn_index=0, role=TurnRole.USER, content="hello"),
        ConversationTurn(turn_index=1, role=TurnRole.ASSISTANT, content="hi there"),
        ConversationTurn(turn_index=2, role=TurnRole.USER, content="more"),
        ConversationTurn(turn_index=3, role=TurnRole.ASSISTANT, content="still here"),
    ]

    updated = await pipeline.maybe_update(summary=summary, all_turns=turns, policy=policy)
    assert "hello" in updated.text
    assert "still here" in updated.text
    assert updated.turn_count == 4


@pytest.mark.asyncio
async def test_summarization_skips_between_intervals():
    pipeline = SummarizationPipeline()
    policy = SummarizationPolicy(summarize_every_n_turns=4)
    summary = SessionSummary(session_id="s1", text="", turn_count=0)
    turns = [
        ConversationTurn(turn_index=0, role=TurnRole.USER, content="one"),
        ConversationTurn(turn_index=1, role=TurnRole.ASSISTANT, content="two"),
    ]
    updated = await pipeline.maybe_update(summary=summary, all_turns=turns, policy=policy)
    assert updated.text == ""
    assert updated.turn_count == 2
