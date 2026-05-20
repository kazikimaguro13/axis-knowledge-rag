"""Unit tests for the knowledge-gap detection store (spec_048)."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest

from backend.src.gap_detection import (
    GapRecord,
    GapStore,
    SqliteGapStore,
    detect_no_info,
    make_gap_store,
)


@pytest.fixture
def store(tmp_path: Path) -> SqliteGapStore:
    s = SqliteGapStore(db_path=str(tmp_path / "gap.db"))
    yield s
    s.close()


# ---------------------------------------------------------------------------
# detect_no_info()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        "提供された資料には記載がありません。",
        "提供された資料には情報がありません",
        "該当する資料は見当たりません。",
        "わかりません。",
        "不明です。",
    ],
)
def test_detect_no_info_japanese(answer: str) -> None:
    assert detect_no_info(answer) is True


@pytest.mark.parametrize(
    "answer",
    [
        "I don't have the information needed to answer.",
        "Sorry — no information available about that.",
    ],
)
def test_detect_no_info_english(answer: str) -> None:
    assert detect_no_info(answer) is True


@pytest.mark.parametrize(
    "answer",
    [
        # Plain citation-bearing answer — must not flag.
        "RAG は Retrieval-Augmented Generation の略です [1]。",
        # Result card style summary.
        "ベクトル検索はコサイン類似度を用います [1][2]。",
        # English answer about a real topic.
        "BM25 is a probabilistic ranking function used by search engines.",
    ],
)
def test_detect_no_info_negative_cases(answer: str) -> None:
    assert detect_no_info(answer) is False


def test_detect_no_info_empty_string_treated_as_gap() -> None:
    # Empty / whitespace responses are functionally equivalent to
    # "I don't know" for the purpose of the report.
    assert detect_no_info("") is True
    assert detect_no_info("   \n  ") is True
    assert detect_no_info(None) is True  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SqliteGapStore
# ---------------------------------------------------------------------------


def test_store_record_low_score(store: SqliteGapStore) -> None:
    gid = store.record(
        query="Kubernetes operator pattern",
        reason="low_score",
        top_score=0.22,
        n_results=3,
    )
    parsed = uuid.UUID(gid)
    assert parsed.version == 4
    rows = store.list_recent(days=7)
    assert len(rows) == 1
    r = rows[0]
    assert isinstance(r, GapRecord)
    assert r.query == "Kubernetes operator pattern"
    assert r.reason == "low_score"
    assert r.top_score == pytest.approx(0.22)
    assert r.n_results == 3


def test_store_record_llm_no_info(store: SqliteGapStore) -> None:
    store.record(
        query="Llama.cpp benchmark",
        reason="llm_no_info",
        top_score=0.78,
        n_results=5,
    )
    rows = store.list_recent(days=7)
    assert rows[0].reason == "llm_no_info"
    # We deliberately keep top_score even when the LLM said "no info" —
    # the report uses it to distinguish "we had docs but LLM refused" from
    # "no docs to begin with".
    assert rows[0].top_score == pytest.approx(0.78)


def test_list_recent_filters_old(
    store: SqliteGapStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.record(query="recent topic", reason="low_score", n_results=1)
    old_ts = time.time() - 30 * 86400
    with store._lock:  # noqa: SLF001 — intentional white-box for test
        store._conn.execute(  # noqa: SLF001
            "INSERT INTO gaps "
            "(gap_id, query, reason, top_score, n_results, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "ancient topic", "no_results", None, 0, old_ts),
        )
        store._conn.commit()  # noqa: SLF001
    rows = store.list_recent(days=7)
    queries = {r.query for r in rows}
    assert "recent topic" in queries
    assert "ancient topic" not in queries
    # The ancient row still exists in the table — only the window filter
    # excludes it.
    assert store.count() == 2


def test_count(store: SqliteGapStore) -> None:
    assert store.count() == 0
    store.record(query="q1", reason="no_results", n_results=0)
    store.record(query="q2", reason="low_score", top_score=0.1, n_results=2)
    assert store.count() == 2


def test_close_idempotent(tmp_path: Path) -> None:
    s = SqliteGapStore(db_path=str(tmp_path / "gap.db"))
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


def test_make_gap_store_disabled() -> None:
    cfg = _FakeCfg(enabled=False, db_path="~/.axis_gap.db")
    assert make_gap_store(cfg) is None


def test_make_gap_store_enabled(tmp_path: Path) -> None:
    cfg = _FakeCfg(enabled=True, db_path=str(tmp_path / "gap.db"))
    s = make_gap_store(cfg)
    assert isinstance(s, GapStore)
    assert s is not None
    s.close()
