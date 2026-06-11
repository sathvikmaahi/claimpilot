"""Tests for session store implementations."""

import pytest

from core.conversation.models import ConversationTurn, SessionStatus, TurnRole
from core.conversation.stores.memory import InMemoryConversationSessionStore
from core.conversation.stores.sqlite import SqliteConversationSessionStore


@pytest.mark.asyncio
async def test_in_memory_store_lifecycle():
    store = InMemoryConversationSessionStore()
    session = await store.create_session(agent_id="chat", user_id="user-1")
    assert session.status == SessionStatus.ACTIVE

    turn = ConversationTurn(turn_index=0, role=TurnRole.USER, content="hello")
    await store.append_turn(session.session_id, turn)
    assert await store.get_turn_count(session.session_id) == 1

    summary = await store.get_summary(session.session_id)
    summary.text = "User said hello."
    await store.save_summary(summary)

    loaded = await store.get_summary(session.session_id)
    assert loaded.text == "User said hello."

    closed = await store.close_session(session.session_id)
    assert closed.status == SessionStatus.CLOSED


@pytest.mark.asyncio
async def test_sqlite_store_persistence(tmp_path):
    db_path = tmp_path / "sessions.db"
    store = SqliteConversationSessionStore(db_path)
    session = await store.create_session(agent_id="chat", user_id="user-2")
    await store.append_turn(
        session.session_id,
        ConversationTurn(turn_index=0, role=TurnRole.USER, content="persist me"),
    )

    store2 = SqliteConversationSessionStore(db_path)
    loaded = await store2.get_session(session.session_id)
    assert loaded is not None
    turns = await store2.get_turns(session.session_id)
    assert turns[0].content == "persist me"
