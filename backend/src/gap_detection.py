"""Knowledge gap detection store (spec_048).

Records search / answer events where the system likely doesn't have
enough information to satisfy the user:

* ``no_results``  — search returned an empty hit list.
* ``low_score``   — top hit fell below ``gap.low_score_threshold``.
* ``llm_no_info`` — the LLM answered "資料に記載がありません" or similar.

Aggregate analytics live in ``evaluation/gap_report.py``. As with
``spec_047``'s feedback store, the MVP scope is intentionally just
*logging* — using the captured gaps to auto-suggest knowledge ingests is
parked for v0.10. Keeping the store behind a small ``GapStore`` Protocol
leaves room for a PostgreSQL / Redis backend later without breaking call
sites.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class GapRecord:
    gap_id: str
    query: str
    reason: str            # "low_score" | "llm_no_info" | "no_results"
    top_score: float | None
    n_results: int
    timestamp: datetime


@runtime_checkable
class GapStore(Protocol):
    def record(
        self,
        *,
        query: str,
        reason: str,
        top_score: float | None = None,
        n_results: int = 0,
    ) -> str: ...

    def list_recent(
        self, *, days: int = 7, limit: int = 1000
    ) -> list[GapRecord]: ...

    def count(self) -> int: ...

    def close(self) -> None: ...


class SqliteGapStore:
    """File-backed gap store using stdlib ``sqlite3`` (no new deps).

    The default path is ``~/.axis_gap.db`` so the file lives next to the
    existing ``~/.axis_feedback.db`` (spec_047) and ``~/.axis_chat.db``
    (spec_036). A single shared connection is reused under a
    ``threading.Lock`` because FastAPI may call ``record`` from multiple
    worker threads on the search / answer paths.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS gaps (
        gap_id TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        reason TEXT NOT NULL,
        top_score REAL,
        n_results INTEGER NOT NULL,
        timestamp REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_gaps_ts ON gaps(timestamp);
    CREATE INDEX IF NOT EXISTS idx_gaps_query ON gaps(query);
    """

    def __init__(self, db_path: str = "~/.axis_gap.db") -> None:
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
        query: str,
        reason: str,
        top_score: float | None = None,
        n_results: int = 0,
    ) -> str:
        if self._conn is None:
            raise RuntimeError("gap store has been closed")
        gid = str(uuid.uuid4())
        ts = datetime.now(UTC).timestamp()
        with self._lock:
            self._conn.execute(
                "INSERT INTO gaps "
                "(gap_id, query, reason, top_score, n_results, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    gid,
                    query,
                    reason,
                    None if top_score is None else float(top_score),
                    int(n_results),
                    ts,
                ),
            )
            self._conn.commit()
        return gid

    def list_recent(
        self, *, days: int = 7, limit: int = 1000
    ) -> list[GapRecord]:
        if self._conn is None:
            raise RuntimeError("gap store has been closed")
        cutoff = datetime.now(UTC).timestamp() - days * 86400
        rows = self._conn.execute(
            "SELECT gap_id, query, reason, top_score, n_results, timestamp "
            "FROM gaps WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
        return [
            GapRecord(
                gap_id=r[0],
                query=r[1],
                reason=r[2],
                top_score=None if r[3] is None else float(r[3]),
                n_results=int(r[4]),
                timestamp=datetime.fromtimestamp(r[5], tz=UTC),
            )
            for r in rows
        ]

    def count(self) -> int:
        if self._conn is None:
            return 0
        return int(
            self._conn.execute("SELECT COUNT(*) FROM gaps").fetchone()[0]
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# "LLM doesn't know" detection
# ---------------------------------------------------------------------------

# Patterns intentionally err on the side of *not* firing — a false negative
# (real "I don't know" answer slipping through) is far cheaper than a false
# positive (a normal answer landing in the gap report). The patterns are
# anchored on standalone declarative phrasing the SYSTEM_PROMPT explicitly
# tells Claude to emit ("提供された資料には記載がありません" etc.).
NO_INFO_PATTERNS: list[str] = [
    # Japanese
    r"資料(に|には)?(は)?(記載|情報|該当)(が)?(ない|ありません|ございません|見当たりません)",
    r"提供された(資料|文書|context|情報)(に|には)?(記載|情報)?(が)?(ない|ありません)",
    r"該当(する|の)?(資料|文書|情報)(は|が)?(ない|ありません|見当たりません)",
    r"情報(が)?(ない|ありません|ございません|不明)です",
    # spec_051 MID-3: "わかりません" / "不明です" must terminate the answer
    # (final sentence), not appear as an aside inside a partial answer
    # like "A は X ですが、B はわかりません、しかし C は Y です。" where it
    # is followed by 、 + more content. Anchor the right side on
    # end-of-string, optionally preceded by a 。 + trailing whitespace.
    r"わかりません(?:。\s*\Z|\Z)",
    r"不明です(?:。\s*\Z|\Z)",
    r"答えられません",
    # English
    r"I (do not|don't) have (the |enough )?information",
    r"no information( available)?",
    r"insufficient (context|information)",
]

_NO_INFO_RE = re.compile("|".join(NO_INFO_PATTERNS), re.IGNORECASE)


def detect_no_info(answer_text: str | None) -> bool:
    """Return ``True`` when the LLM seems to have answered "I don't know".

    Empty / whitespace-only answers are treated as a gap as well — an
    empty model response is equivalent to "no information" for the
    purpose of populating the knowledge-gap report.
    """
    if not answer_text or not answer_text.strip():
        return True
    return bool(_NO_INFO_RE.search(answer_text))


def make_gap_store(cfg) -> GapStore | None:  # type: ignore[no-untyped-def]
    """Build a gap store from ``GapConfig``.

    Returns ``None`` when the feature is disabled — callers should map
    that to a 503 at the API layer rather than silently swallowing
    writes. ``search.py`` / ``rag.py`` simply skip the hook when the
    store is ``None`` (no-op), which keeps ``gap.enabled=false`` truly
    zero-cost on the hot path.
    """
    if not getattr(cfg, "enabled", False):
        return None
    return SqliteGapStore(db_path=getattr(cfg, "db_path", "~/.axis_gap.db"))
