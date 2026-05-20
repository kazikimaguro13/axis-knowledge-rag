"""Unit tests for the active-learning feedback store (spec_047)."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest

from backend.src.feedback import (
    FeedbackRecord,
    FeedbackStore,
    SqliteFeedbackStore,
    make_feedback_store,
)


@pytest.fixture
def store(tmp_path: Path) -> SqliteFeedbackStore:
    s = SqliteFeedbackStore(db_path=str(tmp_path / "fb.db"))
    yield s
    s.close()


def test_record_creates_uuid(store: SqliteFeedbackStore) -> None:
    fid = store.record(query="hello", doc_id="doc_1", rating=1)
    # uuid4 hex form has 36 chars including dashes; this also confirms the
    # return shape is a real UUID rather than a row id.
    parsed = uuid.UUID(fid)
    assert parsed.version == 4


def test_record_persists(store: SqliteFeedbackStore) -> None:
    fid = store.record(query="q", doc_id="d", rating=1, session_id="sid", note="n")
    assert store.count() == 1
    rows = store.list_recent(days=7)
    assert len(rows) == 1
    r = rows[0]
    assert isinstance(r, FeedbackRecord)
    assert r.feedback_id == fid
    assert r.query == "q"
    assert r.doc_id == "d"
    assert r.rating == 1
    assert r.session_id == "sid"
    assert r.note == "n"


def test_list_recent_within_window(store: SqliteFeedbackStore) -> None:
    for i in range(3):
        store.record(query=f"q{i}", doc_id=f"d{i}", rating=1)
    rows = store.list_recent(days=7)
    assert len(rows) == 3
    # Most-recent first (ORDER BY timestamp DESC); the 3 inserts happen in
    # quick succession so we mostly assert ordering doesn't crash on ties.
    assert {r.query for r in rows} == {"q0", "q1", "q2"}


def test_list_recent_filters_old(
    store: SqliteFeedbackStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Insert a record with a backdated timestamp directly via the connection
    # — we don't expose a public knob because production code never needs to
    # fake the clock.
    store.record(query="recent", doc_id="d", rating=1)
    old_ts = time.time() - 30 * 86400  # 30 days ago
    with store._lock:  # noqa: SLF001 — intentional white-box for test
        store._conn.execute(  # noqa: SLF001
            "INSERT INTO feedback "
            "(feedback_id, query, doc_id, rating, session_id, note, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "ancient", "d_old", 1, None, None, old_ts),
        )
        store._conn.commit()  # noqa: SLF001
    rows = store.list_recent(days=7)
    queries = {r.query for r in rows}
    assert "recent" in queries
    assert "ancient" not in queries
    # The ancient row still exists in the table — only the window filter
    # excludes it.
    assert store.count() == 2


def test_count(store: SqliteFeedbackStore) -> None:
    assert store.count() == 0
    store.record(query="a", doc_id="x", rating=1)
    store.record(query="b", doc_id="y", rating=-1)
    assert store.count() == 2


def test_rating_values_accepted(store: SqliteFeedbackStore) -> None:
    # +1 / -1 / 0 are all valid at the storage layer (the API caps to ±1).
    for r in (1, -1, 0):
        store.record(query="q", doc_id="d", rating=r)
    rows = store.list_recent()
    assert sorted(r.rating for r in rows) == [-1, 0, 1]


def test_doc_id_optional(store: SqliteFeedbackStore) -> None:
    # doc_id=None is the "feedback applies to the whole answer" case.
    store.record(query="q", doc_id=None, rating=1)
    rows = store.list_recent()
    assert len(rows) == 1
    assert rows[0].doc_id is None


def test_session_id_optional(store: SqliteFeedbackStore) -> None:
    store.record(query="anon", doc_id="d", rating=1)  # no session_id
    rows = store.list_recent()
    assert rows[0].session_id is None


def test_note_optional(store: SqliteFeedbackStore) -> None:
    store.record(query="q", doc_id="d", rating=1, note=None)
    rows = store.list_recent()
    assert rows[0].note is None


def test_close_idempotent(tmp_path: Path) -> None:
    s = SqliteFeedbackStore(db_path=str(tmp_path / "fb.db"))
    s.close()
    # Second close must not raise — useful when lifespan teardown runs after
    # an error has already triggered a close.
    s.close()
    assert s.count() == 0


# ---------------------------------------------------------------------------
# factory + Protocol conformance
# ---------------------------------------------------------------------------


class _FakeCfg:
    def __init__(self, enabled: bool, db_path: str) -> None:
        self.enabled = enabled
        self.db_path = db_path


def test_make_feedback_store_disabled() -> None:
    cfg = _FakeCfg(enabled=False, db_path="~/.axis_feedback.db")
    assert make_feedback_store(cfg) is None


def test_make_feedback_store_enabled(tmp_path: Path) -> None:
    cfg = _FakeCfg(enabled=True, db_path=str(tmp_path / "fb.db"))
    s = make_feedback_store(cfg)
    assert isinstance(s, FeedbackStore)
    assert s is not None
    s.close()
