"""Factory helpers for the conversation layer."""

from __future__ import annotations

from pathlib import Path

from core.config import Settings
from core.conversation.hooks import HookRunner, build_default_hooks
from core.conversation.memory_adapter import create_memory_adapter
from core.conversation.session_manager import SessionManager
from core.conversation.session_store import ConversationSessionStore
from core.conversation.stores.memory import InMemoryConversationSessionStore
from core.conversation.stores.sqlite import SqliteConversationSessionStore
from core.conversation.summarizer import SummarizationPipeline


def create_conversation_session_store(settings: Settings) -> ConversationSessionStore:
    if settings.conversation_database_url:
        db_path = settings.conversation_database_url.removeprefix("sqlite:///")
        return SqliteConversationSessionStore(Path(db_path))
    return InMemoryConversationSessionStore()


def create_session_manager(settings: Settings) -> SessionManager:
    store = create_conversation_session_store(settings)
    memory = create_memory_adapter(settings)
    hooks = HookRunner(build_default_hooks(memory))
    return SessionManager(
        store=store,
        summarization=SummarizationPipeline(),
        memory=memory,
        hooks=hooks,
    )
