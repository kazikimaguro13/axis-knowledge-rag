"""Persistence-pluggable chat session storage (spec_036).

Three implementations behind a common ``ConversationStore`` Protocol:

- ``MemoryStore`` — thread-safe in-memory dict (v0.7 behaviour, kept for
  tests, fast local runs, and as a fallback when sqlite/redis fail).
- ``SqliteStore`` — file-backed sqlite3 (WAL mode), default for v0.8+.
  Survives process restarts and is safe across uvicorn workers.
- ``RedisStore`` — optional, requires ``pip install -e ".[redis]"``.
  Use this for multi-host deployments.

The factory ``make_conversation_store(chat_cfg)`` picks one of the three
based on ``chat.storage.backend`` (memory / sqlite / redis). Misconfiguration
or missing optional dependency falls back to ``MemoryStore`` with a warning.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Protocol (the v0.8 "contract")
# ---------------------------------------------------------------------------


@runtime_checkable
class ConversationStore(Protocol):
    """Contract for all session storage backends.

    Note: this is a typing.Protocol, not an instantiable class. Concrete
    backends (MemoryStore / SqliteStore / RedisStore) implement this
    structurally — there is no inheritance requirement.
    """

    def get_or_create(self, session_id: str | None = None) -> Session: ...

    def append(self, session_id: str, msg: Message) -> None: ...

    def get_history(
        self, session_id: str, *, last_n_turns: int = 6
    ) -> list[Message]: ...

    def delete(self, session_id: str) -> bool: ...

    def __len__(self) -> int: ...

    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# MemoryStore — v0.7 in-memory implementation, renamed
# ---------------------------------------------------------------------------


class MemoryStore:
    """Thread-safe in-memory session store with TTL + LRU eviction.

    - **TTL**: a session that has not been accessed for ``ttl_seconds`` is
      evicted on the next access.
    - **LRU**: if inserting a new session would push the count above
      ``max_sessions``, the session with the oldest ``last_access`` is
      dropped. Eviction runs after the new session is inserted so the new
      one is never evicted in the same step.

    Identical to the v0.7 ``ConversationStore``; kept as the fast path for
    tests, single-shot scripts, and as a fallback when other backends fail.
    """

    def __init__(self, *, max_sessions: int = 100, ttl_seconds: int = 86400) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()
        self._max = max_sessions
        self._ttl = timedelta(seconds=ttl_seconds)

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
                s = Session(session_id=session_id)
                self._sessions[session_id] = s
                self._evict_lru()
            s.messages.append(msg)
            s.last_access = _utcnow()

    def get_history(
        self, session_id: str, *, last_n_turns: int = 6
    ) -> list[Message]:
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

    def has(self, session_id: str) -> bool:
        """Whether the session exists without bumping its last_access."""
        with self._lock:
            return session_id in self._sessions

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    def close(self) -> None:  # no-op for in-memory
        pass

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
# SqliteStore — file-backed default for v0.8+
# ---------------------------------------------------------------------------


class SqliteStore:
    """File-backed session store using stdlib ``sqlite3``.

    Schema:
        sessions(session_id TEXT PK, last_access REAL)
        messages(id INTEGER PK AUTOINCREMENT, session_id TEXT FK,
                 role TEXT, content TEXT, sources_json TEXT, timestamp REAL)
        INDEX: messages(session_id, id)

    - WAL journal mode enables concurrent reads while a writer holds the lock
    - FOREIGN KEYS ensures DELETE FROM sessions also drops messages
    - ``check_same_thread=False`` because FastAPI's threadpool dispatches
      requests across threads; we guard mutations with our own ``Lock``.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        last_access REAL NOT NULL
    );
    -- spec_042 MID #3: TTL eviction + LRU pick both scan by last_access;
    -- without this index they become O(N) over the whole sessions table.
    CREATE INDEX IF NOT EXISTS idx_sessions_last_access ON sessions(last_access);
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        sources_json TEXT,
        timestamp REAL NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
    """

    def __init__(
        self,
        db_path: str = "~/.axis_chat.db",
        *,
        max_sessions: int = 1000,
        ttl_seconds: int = 86400,
    ) -> None:
        self._db_path = os.path.expanduser(db_path)
        # Ensure parent dir exists (so e.g. data/chat.db works on a fresh checkout).
        parent = os.path.dirname(self._db_path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        self._max = max_sessions
        self._ttl = ttl_seconds
        self._conn: sqlite3.Connection | None = sqlite3.connect(
            self._db_path, check_same_thread=False
        )
        self._conn.executescript(self.SCHEMA)
        # WAL for concurrent reads; FK pragma is per-connection.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.commit()
        self._lock = Lock()
        # Purge any sessions already past TTL when we re-open the DB.
        self._evict_expired_locked()

    # ----- public API ----------------------------------------------------

    def get_or_create(self, session_id: str | None = None) -> Session:
        with self._lock:
            self._evict_expired_locked()
            now = _utcnow()
            conn = self._require_conn()
            if session_id:
                row = conn.execute(
                    "SELECT last_access FROM sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row is not None:
                    conn.execute(
                        "UPDATE sessions SET last_access = ? WHERE session_id = ?",
                        (now.timestamp(), session_id),
                    )
                    conn.commit()
                    return self._load_session_locked(session_id, now)
            new_id = session_id or str(uuid.uuid4())
            conn.execute(
                "INSERT INTO sessions (session_id, last_access) VALUES (?, ?)",
                (new_id, now.timestamp()),
            )
            conn.commit()
            self._evict_lru_locked()
            return Session(session_id=new_id, last_access=now)

    def append(self, session_id: str, msg: Message) -> None:
        with self._lock:
            conn = self._require_conn()
            now = _utcnow()
            # "append on unknown id" → silently create the parent row so the
            # FK doesn't blow up. Mirrors MemoryStore behaviour.
            row = conn.execute(
                "SELECT session_id FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO sessions (session_id, last_access) VALUES (?, ?)",
                    (session_id, now.timestamp()),
                )
                self._evict_lru_locked()
            conn.execute(
                "INSERT INTO messages "
                "(session_id, role, content, sources_json, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    session_id,
                    msg.role,
                    msg.content,
                    json.dumps(msg.sources, ensure_ascii=False),
                    msg.timestamp.timestamp(),
                ),
            )
            conn.execute(
                "UPDATE sessions SET last_access = ? WHERE session_id = ?",
                (now.timestamp(), session_id),
            )
            conn.commit()

    def get_history(
        self, session_id: str, *, last_n_turns: int = 6
    ) -> list[Message]:
        with self._lock:
            conn = self._require_conn()
            # Confirm the session exists — unknown id returns [] like MemoryStore.
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return []
            limit = max(0, last_n_turns) * 2
            if limit == 0:
                return []
            rows = conn.execute(
                "SELECT role, content, sources_json, timestamp FROM messages "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        # ORDER BY DESC LIMIT N gives the newest N rows; reverse to chronological.
        return [self._row_to_msg(r) for r in reversed(rows)]

    def delete(self, session_id: str) -> bool:
        with self._lock:
            conn = self._require_conn()
            cur = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def has(self, session_id: str) -> bool:
        with self._lock:
            conn = self._require_conn()
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            return row is not None

    def __len__(self) -> int:
        with self._lock:
            conn = self._require_conn()
            return int(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None

    # ----- internals -----------------------------------------------------

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SqliteStore connection is already closed")
        return self._conn

    def _load_session_locked(self, session_id: str, last_access: datetime) -> Session:
        conn = self._require_conn()
        rows = conn.execute(
            "SELECT role, content, sources_json, timestamp FROM messages "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        msgs = [self._row_to_msg(r) for r in rows]
        return Session(session_id=session_id, messages=msgs, last_access=last_access)

    @staticmethod
    def _row_to_msg(row: tuple[Any, ...]) -> Message:
        role, content, sources_json, ts = row
        sources = json.loads(sources_json) if sources_json else []
        return Message(
            role=role,
            content=content,
            sources=sources,
            timestamp=datetime.fromtimestamp(ts, tz=UTC),
        )

    def _evict_expired_locked(self) -> None:
        conn = self._require_conn()
        cutoff = (_utcnow() - timedelta(seconds=self._ttl)).timestamp()
        conn.execute("DELETE FROM sessions WHERE last_access < ?", (cutoff,))
        conn.commit()

    def _evict_lru_locked(self) -> None:
        conn = self._require_conn()
        count = int(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
        excess = count - self._max
        if excess <= 0:
            return
        conn.execute(
            "DELETE FROM sessions WHERE session_id IN "
            "(SELECT session_id FROM sessions ORDER BY last_access ASC LIMIT ?)",
            (excess,),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# RedisStore — optional, requires `pip install -e ".[redis]"`
# ---------------------------------------------------------------------------


class RedisStore:
    """Redis-backed session store. Optional dependency.

    Key layout::

        axis:session:{session_id}:meta  → JSON {"last_access": float}
        axis:session:{session_id}:msgs  → LIST of JSON Message blobs

    Per-key TTL is reset on every read / write so an active conversation
    never expires. Use a Standalone Redis (Cluster support is tracked for
    v0.9 / spec_044). LRU/eviction is delegated to Redis' own maxmemory
    policy — clients should configure ``maxmemory-policy allkeys-lru`` if
    they care about a hard cap.
    """

    META_PREFIX = "axis:session"

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        *,
        ttl_seconds: int = 86400,
    ) -> None:
        try:
            import redis  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover - exercised by skipped tests
            raise RuntimeError(
                "RedisStore requires `pip install -e \".[redis]\"`"
            ) from e
        self._redis_mod = redis
        self._url = url
        self._ttl = ttl_seconds
        self._r: Any | None = redis.Redis.from_url(url, decode_responses=True)
        # Eagerly verify the connection so the factory can fall back cleanly.
        self._r.ping()

    # ----- public API ----------------------------------------------------

    def get_or_create(self, session_id: str | None = None) -> Session:
        r = self._require_client()
        new_id = session_id or str(uuid.uuid4())
        meta_key = self._meta_key(new_id)
        msgs_key = self._msgs_key(new_id)
        now = _utcnow()
        existing = r.get(meta_key)
        meta_payload = json.dumps({"last_access": now.timestamp()})
        if existing:
            r.set(meta_key, meta_payload, ex=self._ttl)
            # Bump TTL on the msgs key only if it still exists.
            r.expire(msgs_key, self._ttl)
            return self._load_session(new_id, now)
        r.set(meta_key, meta_payload, ex=self._ttl)
        return Session(session_id=new_id, last_access=now)

    def append(self, session_id: str, msg: Message) -> None:
        r = self._require_client()
        meta_key = self._meta_key(session_id)
        msgs_key = self._msgs_key(session_id)
        now = _utcnow()
        msg_payload = json.dumps(
            {
                "role": msg.role,
                "content": msg.content,
                "sources": msg.sources,
                "timestamp": msg.timestamp.timestamp(),
            },
            ensure_ascii=False,
        )
        pipe = r.pipeline()
        pipe.rpush(msgs_key, msg_payload)
        pipe.expire(msgs_key, self._ttl)
        pipe.set(
            meta_key,
            json.dumps({"last_access": now.timestamp()}),
            ex=self._ttl,
        )
        pipe.execute()

    def get_history(
        self, session_id: str, *, last_n_turns: int = 6
    ) -> list[Message]:
        r = self._require_client()
        if not r.exists(self._meta_key(session_id)):
            return []
        limit = max(0, last_n_turns) * 2
        if limit == 0:
            return []
        # LRANGE with negative indices returns the tail. -limit..-1 yields up
        # to `limit` newest entries; if the list is shorter, returns all.
        rows = r.lrange(self._msgs_key(session_id), -limit, -1)
        return [self._json_to_msg(row) for row in rows]

    def delete(self, session_id: str) -> bool:
        r = self._require_client()
        meta_key = self._meta_key(session_id)
        msgs_key = self._msgs_key(session_id)
        # DEL returns the count of keys actually removed; either ≥1 → True.
        return int(r.delete(meta_key, msgs_key)) > 0

    def has(self, session_id: str) -> bool:
        r = self._require_client()
        return bool(r.exists(self._meta_key(session_id)))

    def __len__(self) -> int:
        r = self._require_client()
        count = 0
        for _ in r.scan_iter(f"{self.META_PREFIX}:*:meta"):
            count += 1
        return count

    def close(self) -> None:
        if self._r is not None:
            try:
                self._r.close()
            finally:
                self._r = None

    # ----- internals -----------------------------------------------------

    def _require_client(self) -> Any:
        if self._r is None:
            raise RuntimeError("RedisStore client is already closed")
        return self._r

    def _meta_key(self, session_id: str) -> str:
        return f"{self.META_PREFIX}:{session_id}:meta"

    def _msgs_key(self, session_id: str) -> str:
        return f"{self.META_PREFIX}:{session_id}:msgs"

    def _load_session(self, session_id: str, last_access: datetime) -> Session:
        r = self._require_client()
        rows = r.lrange(self._msgs_key(session_id), 0, -1)
        msgs = [self._json_to_msg(row) for row in rows]
        return Session(session_id=session_id, messages=msgs, last_access=last_access)

    @staticmethod
    def _json_to_msg(payload: str) -> Message:
        obj = json.loads(payload)
        return Message(
            role=obj["role"],
            content=obj["content"],
            sources=obj.get("sources", []) or [],
            timestamp=datetime.fromtimestamp(obj["timestamp"], tz=UTC),
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_conversation_store(chat_cfg: Any) -> ConversationStore:
    """Construct a conversation store from a ChatConfig-shaped object.

    Expected attributes on ``chat_cfg``:

    - ``max_sessions: int``
    - ``ttl_seconds: int``
    - ``storage.backend: str``  ("memory" | "sqlite" | "redis")
    - ``storage.sqlite_path: str``
    - ``storage.redis_url: str``

    Misconfiguration (unknown backend, redis not installed, redis unreachable)
    logs a warning and falls back to ``MemoryStore`` so the API still boots.
    """
    backend = (chat_cfg.storage.backend or "memory").lower()
    if backend == "memory":
        return MemoryStore(
            max_sessions=chat_cfg.max_sessions,
            ttl_seconds=chat_cfg.ttl_seconds,
        )
    if backend == "sqlite":
        return SqliteStore(
            db_path=chat_cfg.storage.sqlite_path,
            max_sessions=chat_cfg.max_sessions,
            ttl_seconds=chat_cfg.ttl_seconds,
        )
    if backend == "redis":
        try:
            return RedisStore(
                url=chat_cfg.storage.redis_url,
                ttl_seconds=chat_cfg.ttl_seconds,
            )
        except Exception as e:  # noqa: BLE001 — redis client raises many types
            logger.warning(
                "RedisStore unavailable (%s); falling back to MemoryStore", e
            )
            return MemoryStore(
                max_sessions=chat_cfg.max_sessions,
                ttl_seconds=chat_cfg.ttl_seconds,
            )
    logger.warning(
        "unknown chat.storage.backend=%r; falling back to MemoryStore", backend
    )
    return MemoryStore(
        max_sessions=chat_cfg.max_sessions,
        ttl_seconds=chat_cfg.ttl_seconds,
    )


# ---------------------------------------------------------------------------
# Module-level default store (used by FastAPI / rag.chat() when none injected)
# ---------------------------------------------------------------------------


_default_store: ConversationStore | None = None


def get_default_store() -> ConversationStore:
    """Return the lazily-created process-wide default store.

    Defaults to an in-memory store for back-compat with v0.7 callers that
    didn't explicitly wire one in; the API lifespan replaces this via
    ``configure_default_store(make_conversation_store(chat_cfg))``.
    """
    global _default_store
    if _default_store is None:
        _default_store = MemoryStore()
    return _default_store


def configure_default_store(store: ConversationStore) -> None:
    """Replace the process-wide default store (for tests / FastAPI lifespan)."""
    global _default_store
    _default_store = store


def reset_default_store() -> None:
    """Drop the process-wide default store. Used by tests."""
    global _default_store
    _default_store = None
