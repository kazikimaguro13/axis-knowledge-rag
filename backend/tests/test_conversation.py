"""Tests for the in-memory ConversationStore (spec_032)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Thread

import pytest

from backend.src.conversation import (
    ConversationStore,
    Message,
    Session,
    configure_default_store,
    get_default_store,
    reset_default_store,
)


@pytest.fixture
def store() -> ConversationStore:
    return ConversationStore(max_sessions=10, ttl_seconds=3600)


def test_get_or_create_new_session(store: ConversationStore) -> None:
    s = store.get_or_create()
    assert s.session_id
    assert isinstance(s, Session)
    assert s.messages == []
    # UUID4 string has 36 chars
    assert len(s.session_id) == 36


def test_get_or_create_existing(store: ConversationStore) -> None:
    a = store.get_or_create()
    b = store.get_or_create(a.session_id)
    assert a.session_id == b.session_id
    assert a is b  # same object reference


def test_get_or_create_with_explicit_new_id(store: ConversationStore) -> None:
    s = store.get_or_create("my-custom-id")
    assert s.session_id == "my-custom-id"
    s2 = store.get_or_create("my-custom-id")
    assert s2 is s


def test_append_and_history(store: ConversationStore) -> None:
    s = store.get_or_create()
    store.append(s.session_id, Message(role="user", content="hi"))
    store.append(s.session_id, Message(role="assistant", content="hello"))
    hist = store.get_history(s.session_id, last_n_turns=6)
    assert len(hist) == 2
    assert hist[0].role == "user"
    assert hist[0].content == "hi"
    assert hist[1].role == "assistant"


def test_history_truncation(store: ConversationStore) -> None:
    s = store.get_or_create()
    # 6 messages = 3 turns
    for i in range(6):
        role = "user" if i % 2 == 0 else "assistant"
        store.append(s.session_id, Message(role=role, content=f"msg{i}"))
    hist = store.get_history(s.session_id, last_n_turns=2)  # 2 turns = 4 messages
    assert len(hist) == 4
    assert hist[0].content == "msg2"
    assert hist[-1].content == "msg5"


def test_get_history_unknown_session_returns_empty(store: ConversationStore) -> None:
    assert store.get_history("does-not-exist") == []


def test_ttl_eviction() -> None:
    store = ConversationStore(max_sessions=10, ttl_seconds=60)
    s = store.get_or_create()
    # Force last_access into the distant past.
    s.last_access = datetime.now(UTC) - timedelta(seconds=3600)
    # Any new get_or_create call triggers _evict_expired().
    s2 = store.get_or_create()
    assert s2.session_id != s.session_id
    assert s.session_id not in store._sessions  # noqa: SLF001


def test_lru_eviction() -> None:
    store = ConversationStore(max_sessions=2, ttl_seconds=3600)
    a = store.get_or_create("a")
    b = store.get_or_create("b")
    # Force "a" to be the oldest, then add a third — "a" should be evicted.
    a.last_access = datetime.now(UTC) - timedelta(seconds=10)
    b.last_access = datetime.now(UTC) - timedelta(seconds=5)
    store.get_or_create("c")
    assert "a" not in store._sessions  # noqa: SLF001
    assert "b" in store._sessions  # noqa: SLF001
    assert "c" in store._sessions  # noqa: SLF001
    assert len(store) == 2


def test_delete_session(store: ConversationStore) -> None:
    s = store.get_or_create()
    assert store.delete(s.session_id) is True
    assert store.delete(s.session_id) is False
    # Subsequent get_or_create with same id is a fresh session.
    s2 = store.get_or_create(s.session_id)
    assert s2.messages == []


def test_thread_safety() -> None:
    store = ConversationStore(max_sessions=100, ttl_seconds=3600)
    s = store.get_or_create("shared")

    def writer(n: int) -> None:
        for i in range(10):
            store.append(s.session_id, Message(role="user", content=f"{n}:{i}"))

    threads = [Thread(target=writer, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 10 threads * 10 messages each = 100 messages, none lost
    assert len(store.get_history(s.session_id, last_n_turns=999)) == 100


def test_default_store_lifecycle() -> None:
    reset_default_store()
    s1 = get_default_store()
    s2 = get_default_store()
    assert s1 is s2
    custom = ConversationStore(max_sessions=5)
    configure_default_store(custom)
    assert get_default_store() is custom
    reset_default_store()
    assert get_default_store() is not custom


def test_append_on_unknown_session_creates_it(store: ConversationStore) -> None:
    store.append("brand-new", Message(role="user", content="hi"))
    assert "brand-new" in store._sessions  # noqa: SLF001
    assert store.get_history("brand-new")[-1].content == "hi"
