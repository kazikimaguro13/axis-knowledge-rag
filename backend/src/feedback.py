"""User feedback storage for active learning (spec_047).

Tracks 👍/👎 signals on search results / chat answers, plus the originating
query, doc_id, session_id, and timestamp. Aggregate analytics live in
``evaluation/feedback_report.py``.

The MVP scope is intentionally just **logging** — automatic
weight-tuning over the recorded signals is parked for v0.10. Keeping the
store behind a small ``FeedbackStore`` Protocol leaves room for a
PostgreSQL / Redis backend later without breaking call sites.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class FeedbackRecord:
    feedback_id: str
    query: str | None
    doc_id: str | None  # null if feedback applies to the whole answer
    rating: int  # +1 (helpful) / -1 (not helpful) / 0 (neutral)
    session_id: str | None
    note: str | None
    timestamp: datetime


@runtime_checkable
class FeedbackStore(Protocol):
    def record(
        self,
        *,
        query: str | None,
        doc_id: str | None,
        rating: int,
        session_id: str | None = None,
        note: str | None = None,
    ) -> str: ...

    def list_recent(
        self, *, days: int = 7, limit: int = 1000
    ) -> list[FeedbackRecord]: ...

    def count(self) -> int: ...

    def close(self) -> None: ...


class SqliteFeedbackStore:
    """File-backed feedback store using stdlib ``sqlite3`` (no new deps).

    The default path is ``~/.axis_feedback.db`` so the file lives next to
    the existing ``~/.axis_chat.db`` from spec_036. A single shared
    connection is reused under a ``threading.Lock`` because FastAPI may
    call ``record`` from multiple worker threads.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS feedback (
        feedback_id TEXT PRIMARY KEY,
        query TEXT,
        doc_id TEXT,
        rating INTEGER NOT NULL,
        session_id TEXT,
        note TEXT,
        timestamp REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_feedback_ts ON feedback(timestamp);
    CREATE INDEX IF NOT EXISTS idx_feedback_doc ON feedback(doc_id);
    """

    def __init__(self, db_path: str = "~/.axis_feedback.db") -> None:
        self._db_path = Path(os.path.expanduser(db_path))
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = sqlite3.connect(
            str(self._db_path), check_same_thread=False
        )
        self._conn.executescript(self.SCHEMA)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.commit()
        self._lock = threading.Lock()

    def record(
        self,
        *,
        query: str | None = None,
        doc_id: str | None = None,
        rating: int,
        session_id: str | None = None,
        note: str | None = None,
    ) -> str:
        if self._conn is None:
            raise RuntimeError("feedback store has been closed")
        fid = str(uuid.uuid4())
        ts = datetime.now(UTC).timestamp()
        with self._lock:
            self._conn.execute(
                "INSERT INTO feedback "
                "(feedback_id, query, doc_id, rating, session_id, note, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (fid, query, doc_id, int(rating), session_id, note, ts),
            )
            self._conn.commit()
        return fid

    def list_recent(
        self, *, days: int = 7, limit: int = 1000
    ) -> list[FeedbackRecord]:
        if self._conn is None:
            raise RuntimeError("feedback store has been closed")
        cutoff = datetime.now(UTC).timestamp() - days * 86400
        rows = self._conn.execute(
            "SELECT feedback_id, query, doc_id, rating, session_id, note, timestamp "
            "FROM feedback WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
        return [
            FeedbackRecord(
                feedback_id=r[0],
                query=r[1],
                doc_id=r[2],
                rating=int(r[3]),
                session_id=r[4],
                note=r[5],
                timestamp=datetime.fromtimestamp(r[6], tz=UTC),
            )
            for r in rows
        ]

    def count(self) -> int:
        if self._conn is None:
            return 0
        return int(
            self._conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def make_feedback_store(cfg) -> FeedbackStore | None:  # type: ignore[no-untyped-def]
    """Build a feedback store from ``FeedbackConfig``.

    Returns ``None`` when the feature is disabled — callers should map
    that to a 503 at the API layer rather than silently swallowing
    writes.
    """
    if not getattr(cfg, "enabled", False):
        return None
    return SqliteFeedbackStore(db_path=getattr(cfg, "db_path", "~/.axis_feedback.db"))
