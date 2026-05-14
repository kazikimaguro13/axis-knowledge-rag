"""Tests for the ConversationStore protocol + Memory/SQLite implementations.

spec_032 introduced the in-memory store; spec_036 extracted it behind a
Protocol and added SqliteStore + RedisStore. The common API contract is
exercised here against MemoryStore and SqliteStore via ``parametrize``.
Redis lives in ``test_conversation_redis.py`` (skipif when not running),
SQLite-only features (persistence, WAL) live in ``test_conversation_sqlite.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread

import pytest

from backend.src.conversation import (
    ConversationStore,
    MemoryStore,
    Message,
    Session,
    SqliteStore,
    configure_default_store,
    get_default_store,
    reset_default_store,
)

# ---------------------------------------------------------------------------
# Shared parametrized fixture: same suite against Memory + SQLite
# ---------------------------------------------------------------------------


@pytest.fixture
def store(request: pytest.FixtureRequest, tmp_path: Path) -> ConversationStore:
    backend = request.param
    if backend == "memory":
        s: ConversationStore = MemoryStore(max_sessions=10, ttl_seconds=3600)
    elif backend == "sqlite":
        s = SqliteStore(
            db_path=str(tmp_path / "test.db"),
            max_sessions=10,
            ttl_seconds=3600,
        )
    else:  # pragma: no cover - typo guard
        raise ValueError(f"unknown backend: {backend}")
    try:
        yield s
    finally:
        s.close()


pytestmark_common = pytest.mark.parametrize("store", ["memory", "sqlite"], indirect=True)


# ---------------------------------------------------------------------------
# Common contract: every backend must satisfy these.
# ---------------------------------------------------------------------------


@pytestmark_common
def test_get_or_create_new_session(store: ConversationStore) -> None:
    s = store.get_or_create()
    assert s.session_id
    assert isinstance(s, Session)
    assert s.messages == []
    # UUID4 string has 36 chars
    assert len(s.session_id) == 36


@pytestmark_common
def test_get_or_create_existing(store: ConversationStore) -> None:
    a = store.get_or_create()
    b = store.get_or_create(a.session_id)
    assert a.session_id == b.session_id
    # Note: identity (a is b) is only guaranteed for MemoryStore — SQLite
    # round-trips through the DB so each call returns a fresh Session object.


@pytestmark_common
def test_get_or_create_with_explicit_new_id(store: ConversationStore) -> None:
    s = store.get_or_create("my-custom-id")
    assert s.session_id == "my-custom-id"
    s2 = store.get_or_create("my-custom-id")
    assert s2.session_id == s.session_id


@pytestmark_common
def test_append_and_history(store: ConversationStore) -> None:
    s = store.get_or_create()
    store.append(s.session_id, Message(role="user", content="hi"))
    store.append(s.session_id, Message(role="assistant", content="hello"))
    hist = store.get_history(s.session_id, last_n_turns=6)
    assert len(hist) == 2
    assert hist[0].role == "user"
    assert hist[0].content == "hi"
    assert hist[1].role == "assistant"


@pytestmark_common
def test_append_preserves_sources(store: ConversationStore) -> None:
    s = store.get_or_create()
    sources = [{"id": "doc_001", "title": "title", "score": 0.9}]
    store.append(
        s.session_id, Message(role="assistant", content="answer", sources=sources)
    )
    hist = store.get_history(s.session_id, last_n_turns=6)
    assert len(hist) == 1
    assert hist[0].sources == sources


@pytestmark_common
def test_history_truncation(store: ConversationStore) -> None:
    s = store.get_or_create()
    for i in range(6):
        role = "user" if i % 2 == 0 else "assistant"
        store.append(s.session_id, Message(role=role, content=f"msg{i}"))
    hist = store.get_history(s.session_id, last_n_turns=2)  # 2 turns = 4 messages
    assert len(hist) == 4
    assert hist[0].content == "msg2"
    assert hist[-1].content == "msg5"


@pytestmark_common
def test_history_zero_turns(store: ConversationStore) -> None:
    s = store.get_or_create()
    store.append(s.session_id, Message(role="user", content="hi"))
    assert store.get_history(s.session_id, last_n_turns=0) == []


@pytestmark_common
def test_get_history_unknown_session_returns_empty(store: ConversationStore) -> None:
    assert store.get_history("does-not-exist") == []


@pytestmark_common
def test_delete_session(store: ConversationStore) -> None:
    s = store.get_or_create()
    assert store.delete(s.session_id) is True
    assert store.delete(s.session_id) is False
    # After delete + recreate, history is empty again.
    s2 = store.get_or_create(s.session_id)
    assert store.get_history(s2.session_id) == []


@pytestmark_common
def test_len(store: ConversationStore) -> None:
    assert len(store) == 0
    store.get_or_create("a")
    store.get_or_create("b")
    assert len(store) == 2
    store.delete("a")
    assert len(store) == 1


@pytestmark_common
def test_append_on_unknown_session_creates_it(store: ConversationStore) -> None:
    # Mirrors MemoryStore behaviour: appending to an unknown id silently
    # provisions the session so callers don't have to pre-create.
    store.append("brand-new", Message(role="user", content="hi"))
    hist = store.get_history("brand-new")
    assert hist
    assert hist[-1].content == "hi"


@pytestmark_common
def test_thread_safety(store: ConversationStore) -> None:
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


# ---------------------------------------------------------------------------
# MemoryStore-specific behaviour (TTL / LRU eviction tied to in-memory state).
# SqliteStore's eviction is covered in test_conversation_sqlite.py.
# ---------------------------------------------------------------------------


def test_memory_ttl_eviction() -> None:
    store = MemoryStore(max_sessions=10, ttl_seconds=60)
    s = store.get_or_create()
    # Force last_access into the distant past.
    s.last_access = datetime.now(UTC) - timedelta(seconds=3600)
    # Any new get_or_create call triggers _evict_expired().
    s2 = store.get_or_create()
    assert s2.session_id != s.session_id
    assert s.session_id not in store._sessions  # noqa: SLF001


def test_memory_lru_eviction() -> None:
    store = MemoryStore(max_sessions=2, ttl_seconds=3600)
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


# ---------------------------------------------------------------------------
# Module-level default store helpers
# ---------------------------------------------------------------------------


def test_default_store_lifecycle() -> None:
    reset_default_store()
    s1 = get_default_store()
    s2 = get_default_store()
    assert s1 is s2
    custom = MemoryStore(max_sessions=5)
    configure_default_store(custom)
    assert get_default_store() is custom
    reset_default_store()
    assert get_default_store() is not custom


# ---------------------------------------------------------------------------
# Protocol structural check (runtime_checkable Protocol)
# ---------------------------------------------------------------------------


def test_memory_store_satisfies_protocol() -> None:
    assert isinstance(MemoryStore(), ConversationStore)


def test_sqlite_store_satisfies_protocol(tmp_path: Path) -> None:
    store = SqliteStore(db_path=str(tmp_path / "proto.db"))
    try:
        assert isinstance(store, ConversationStore)
    finally:
        store.close()
