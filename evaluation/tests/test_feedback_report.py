"""Unit tests for the weekly feedback report renderer (spec_047)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.src.feedback import SqliteFeedbackStore
from evaluation.feedback_report import generate_report, save_report_to_file


@pytest.fixture
def store(tmp_path: Path) -> SqliteFeedbackStore:
    s = SqliteFeedbackStore(db_path=str(tmp_path / "fb.db"))
    yield s
    s.close()


def test_empty_report_message(store: SqliteFeedbackStore) -> None:
    md = generate_report(store, days=7)
    assert "Feedback report" in md
    assert "No feedback recorded" in md


def test_top_queries_in_report(store: SqliteFeedbackStore) -> None:
    # "RAG とは?" appears 3x, "BM25" 1x → top-queries section orders by count.
    for _ in range(3):
        store.record(query="RAG とは?", doc_id="d_rag", rating=1)
    store.record(query="BM25", doc_id="d_bm25", rating=1)
    md = generate_report(store, days=7)
    assert "Top queries" in md
    assert "'RAG とは?'" in md
    assert "3 interactions" in md
    assert "'BM25'" in md


def test_unpopular_docs_section(store: SqliteFeedbackStore, tmp_path: Path) -> None:
    # `d_bad` gets 3 👎 and 0 👍 → must land in the "Unpopular docs" list.
    for _ in range(3):
        store.record(query="q", doc_id="d_bad", rating=-1)
    store.record(query="q", doc_id="d_good", rating=1)
    md = generate_report(store, days=7)
    assert "Unpopular docs" in md
    assert "`d_bad`" in md
    assert "net -3" in md
    # And save_report_to_file should drop a YYYY-WW.md under output_dir.
    path = save_report_to_file(
        store, days=7, output_dir=str(tmp_path / "reports")
    )
    written = Path(path)
    assert written.exists()
    assert written.name.endswith(".md")
    assert "Unpopular docs" in written.read_text(encoding="utf-8")
