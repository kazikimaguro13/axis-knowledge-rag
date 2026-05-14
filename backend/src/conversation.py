"""In-memory chat session storage with TTL + LRU eviction.

Provides ``ConversationStore`` for keeping short-lived conversational state
in the FastAPI / MCP process. v0.7 deliberately avoids Redis or DB
persistence — single worker, in-process only. Redis-backed multi-worker
storage is tracked as a v0.8 candidate (spec_037).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str
    sources: list[dict[str, Any]] = field(default_factory=list)  # assistant のみ
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class Session:
    session_id: str
    messages: list[Message] = field(default_factory=list)
    last_access: datetime = field(default_factory=_utcnow)


class ConversationStore:
    """Thread-safe in-memory session store with TTL + LRU eviction.

    - **TTL**: a session that has not been accessed for ``ttl_seconds`` is
      evicted on the next access.
    - **LRU**: if inserting a new session would push the count above
      ``max_sessions``, the session with the oldest ``last_access`` is
      dropped. Eviction runs after the new session is inserted so the new
      one is never evicted in the same step.
    """

    def __init__(self, *, max_sessions: int = 100, ttl_seconds: int = 86400) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()
        self._max = max_sessions
        self._ttl = timedelta(seconds=ttl_seconds)

    # ----- public API ----------------------------------------------------

    def get_or_create(self, session_id: str | None = None) -> Session:
        with self._lock:
            self._evict_expired()
            if session_id and session_id in self._sessions:
                s = self._sessions[session_id]
                s.last_access = _utcnow()
                return s
            new_id = session_id or str(uuid.uuid4())
            s = Session(session_id=new_id)
            self._sessions[new_id] = s
            self._evict_lru()
            return s

    def append(self, session_id: str, msg: Message) -> None:
        with self._lock:
            s = self._sessions.get(session_id)
            if s is None:
                # silently create — append on unknown id is treated as "start fresh"
                s = Session(session_id=session_id)
                self._sessions[session_id] = s
                self._evict_lru()
            s.messages.append(msg)
            s.last_access = _utcnow()

    def get_history(
        self, session_id: str, *, last_n_turns: int = 6
    ) -> list[Message]:
        """Return up to ``last_n_turns * 2`` most recent messages.

        A "turn" is a user + assistant pair, so 6 turns = 12 messages.
        Returns an empty list if the session is unknown.
        """
        with self._lock:
            s = self._sessions.get(session_id)
            if s is None:
                return []
            limit = max(0, last_n_turns) * 2
            if limit == 0:
                return []
            return list(s.messages[-limit:])

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def __len__(self) -> int:  # convenience for tests
        with self._lock:
            return len(self._sessions)

    # ----- internals -----------------------------------------------------

    def _evict_expired(self) -> None:
        now = _utcnow()
        expired = [
            sid for sid, s in self._sessions.items() if now - s.last_access > self._ttl
        ]
        for sid in expired:
            self._sessions.pop(sid, None)

    def _evict_lru(self) -> None:
        while len(self._sessions) > self._max:
            victim = min(
                self._sessions.values(), key=lambda s: s.last_access
            ).session_id
            self._sessions.pop(victim, None)


# ---------------------------------------------------------------------------
# Module-level default store (used by FastAPI / rag.chat() when none injected)
# ---------------------------------------------------------------------------

_default_store: ConversationStore | None = None


def get_default_store() -> ConversationStore:
    """Return the lazily-created process-wide default store."""
    global _default_store
    if _default_store is None:
        _default_store = ConversationStore()
    return _default_store


def configure_default_store(store: ConversationStore) -> None:
    """Replace the process-wide default store (for tests / FastAPI lifespan)."""
    global _default_store
    _default_store = store


def reset_default_store() -> None:
    """Drop the process-wide default store. Used by tests."""
    global _default_store
    _default_store = None
