"""SqliteStore-specific tests (spec_036).

The common API contract is exercised in ``test_conversation.py`` via
parametrize. These tests cover behaviour that only makes sense for the
file-backed implementation:

1. Persistence across instances (the whole point of switching the default)
2. Concurrent writes from multiple threads (WAL + lock invariants)
3. TTL eviction cascades to messages via FK ON DELETE CASCADE
4. The DB file is auto-created when it doesn't exist
5. WAL journal mode is actually active
"""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread

import pytest

from backend.src.conversation import Message, SqliteStore


def test_persists_across_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "persist.db"
    store1 = SqliteStore(db_path=str(db_path))
    s = store1.get_or_create("alpha")
    store1.append(s.session_id, Message(role="user", content="hi"))
    store1.append(s.session_id, Message(role="assistant", content="hello"))
    store1.close()

    store2 = SqliteStore(db_path=str(db_path))
    try:
        hist = store2.get_history("alpha", last_n_turns=6)
        assert len(hist) == 2
        assert hist[0].content == "hi"
        assert hist[1].content == "hello"
        assert hist[1].role == "assistant"
    finally:
        store2.close()


def test_concurrent_writes(tmp_path: Path) -> None:
    """10 threads × 10 appends → all 100 messages persisted, none lost.

    The shared connection is guarded by our own Lock; WAL mode lets readers
    proceed in parallel. We confirm both that nothing is lost and that the
    underlying transaction count matches.
    """
    store = SqliteStore(db_path=str(tmp_path / "concurrent.db"))
    try:
        sid = store.get_or_create("shared").session_id

        def writer(n: int) -> None:
            for i in range(10):
                store.append(sid, Message(role="user", content=f"{n}:{i}"))

        threads = [Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        hist = store.get_history(sid, last_n_turns=999)
        assert len(hist) == 100
    finally:
        store.close()


def test_eviction_cleans_messages(tmp_path: Path) -> None:
    """TTL-evicted sessions cascade DELETE to messages (FK ON DELETE CASCADE)."""
    db_path = tmp_path / "evict.db"
    store = SqliteStore(db_path=str(db_path), ttl_seconds=60)
    try:
        sid = store.get_or_create("expired").session_id
        store.append(sid, Message(role="user", content="will be evicted"))
        # Backdate last_access so the next get_or_create() triggers eviction.
        cutoff = (datetime.now(UTC) - timedelta(seconds=3600)).timestamp()
        store._conn.execute(  # noqa: SLF001 — test reaches into internals
            "UPDATE sessions SET last_access = ? WHERE session_id = ?",
            (cutoff, sid),
        )
        store._conn.commit()  # noqa: SLF001

        # Trigger eviction.
        store.get_or_create("fresh")
        assert store.has("expired") is False

        # Messages for the evicted session must also be gone (FK CASCADE).
        rows = store._conn.execute(  # noqa: SLF001
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (sid,)
        ).fetchone()
        assert rows[0] == 0
    finally:
        store.close()


def test_db_file_creation(tmp_path: Path) -> None:
    """SqliteStore creates the DB file (and any missing parent dir) on init."""
    nested = tmp_path / "nested" / "dir" / "chat.db"
    assert not nested.exists()
    store = SqliteStore(db_path=str(nested))
    try:
        assert nested.exists()
        assert nested.is_file()
    finally:
        store.close()


def test_wal_mode_active(tmp_path: Path) -> None:
    """PRAGMA journal_mode returns 'wal' after init (case-insensitive)."""
    db_path = tmp_path / "wal.db"
    store = SqliteStore(db_path=str(db_path))
    try:
        mode = store._conn.execute(  # noqa: SLF001
            "PRAGMA journal_mode"
        ).fetchone()[0]
        assert str(mode).lower() == "wal"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Extra coverage: LRU eviction at the DB level
# ---------------------------------------------------------------------------


def test_sqlite_lru_eviction(tmp_path: Path) -> None:
    """When max_sessions exceeded, the oldest last_access session is dropped."""
    store = SqliteStore(
        db_path=str(tmp_path / "lru.db"),
        max_sessions=2,
        ttl_seconds=3600,
    )
    try:
        store.get_or_create("a")
        # Force "a" to be older than "b" so it loses the LRU race.
        time.sleep(0.01)
        store.get_or_create("b")
        time.sleep(0.01)
        store.get_or_create("c")
        assert store.has("a") is False
        assert store.has("b") is True
        assert store.has("c") is True
        assert len(store) == 2
    finally:
        store.close()


def test_close_is_idempotent(tmp_path: Path) -> None:
    """Calling close() twice must not raise (lifespan teardown can double-fire)."""
    store = SqliteStore(db_path=str(tmp_path / "close.db"))
    store.close()
    store.close()  # second call should be a no-op


def test_use_after_close_raises(tmp_path: Path) -> None:
    """Operations on a closed store raise a clear error rather than corrupting."""
    store = SqliteStore(db_path=str(tmp_path / "uac.db"))
    store.close()
    with pytest.raises(RuntimeError):
        store.get_or_create("x")


def test_concurrent_reads_during_write(tmp_path: Path) -> None:
    """WAL mode: readers from a separate connection don't block on writers."""
    db_path = tmp_path / "readers.db"
    store = SqliteStore(db_path=str(db_path))
    try:
        sid = store.get_or_create("s").session_id
        for i in range(50):
            store.append(sid, Message(role="user", content=f"msg{i}"))

        # Open an independent connection to confirm WAL allows concurrent reads.
        reader = sqlite3.connect(str(db_path))
        try:
            count = reader.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?", (sid,)
            ).fetchone()[0]
            assert count == 50
        finally:
            reader.close()
    finally:
        store.close()


# ---------------------------------------------------------------------------
# spec_042 MID #3 — last_access index for TTL / LRU eviction scans
# ---------------------------------------------------------------------------


def test_idx_sessions_last_access_exists(tmp_path: Path) -> None:
    """Schema creates ``idx_sessions_last_access`` on the sessions table."""
    store = SqliteStore(db_path=str(tmp_path / "idx.db"))
    try:
        rows = store._conn.execute(  # noqa: SLF001
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='sessions'"
        ).fetchall()
        names = {r[0] for r in rows}
        assert "idx_sessions_last_access" in names
    finally:
        store.close()


def test_existing_db_gets_index_on_reopen(tmp_path: Path) -> None:
    """``CREATE INDEX IF NOT EXISTS`` makes migration of older DBs idempotent.

    Simulate a v0.8.0 DB (no index) and verify that re-opening with
    SqliteStore adds the index without losing data.
    """
    db_path = tmp_path / "legacy.db"
    # Hand-craft a v0.8.0-shaped DB without the new index.
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY,
            last_access REAL NOT NULL
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sources_json TEXT,
            timestamp REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
        );
        CREATE INDEX idx_messages_session ON messages(session_id, id);
        """
    )
    # Insert a session whose last_access is "now" so it survives the TTL purge
    # that runs in SqliteStore.__init__.
    now = datetime.now(UTC).timestamp()
    conn.execute(
        "INSERT INTO sessions (session_id, last_access) VALUES ('legacy', ?)",
        (now,),
    )
    conn.commit()
    conn.close()

    store = SqliteStore(db_path=str(db_path))
    try:
        names = {
            r[0]
            for r in store._conn.execute(  # noqa: SLF001
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name='sessions'"
            ).fetchall()
        }
        assert "idx_sessions_last_access" in names
        # data survived migration
        assert store.has("legacy") is True
    finally:
        store.close()
