"""Unit tests for the weekly knowledge-gap report renderer (spec_048)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.src.gap_detection import SqliteGapStore
from evaluation.gap_report import generate_report, save_report_to_file


@pytest.fixture
def store(tmp_path: Path) -> SqliteGapStore:
    s = SqliteGapStore(db_path=str(tmp_path / "gap.db"))
    yield s
    s.close()


def test_empty_report_placeholder(store: SqliteGapStore) -> None:
    md = generate_report(store, days=7)
    assert "Knowledge gap report" in md
    assert "No knowledge gaps detected" in md


def test_top_queries_section(store: SqliteGapStore) -> None:
    # "Kubernetes operator pattern" → 3x low_score; "Llama.cpp benchmark" → 2x llm_no_info.
    for _ in range(3):
        store.record(
            query="Kubernetes operator pattern",
            reason="low_score",
            top_score=0.22,
            n_results=2,
        )
    for _ in range(2):
        store.record(
            query="Llama.cpp benchmark",
            reason="llm_no_info",
            top_score=0.71,
            n_results=4,
        )
    md = generate_report(store, days=7)
    assert "Top unsatisfied queries" in md
    assert "Kubernetes operator pattern" in md
    assert "Llama.cpp benchmark" in md
    # Count + reason annotations + avg score.
    assert "3x" in md
    assert "low_score:3" in md
    assert "llm_no_info:2" in md
    assert "avg top_score=" in md


def test_recommendation_section_and_save(
    store: SqliteGapStore, tmp_path: Path
) -> None:
    store.record(query="some unsatisfied topic", reason="no_results", n_results=0)
    md = generate_report(store, days=7)
    assert "推奨アクション" in md
    assert "examples/knowledge/" in md
    # Reason totals appear in the header summary.
    assert "no_results" in md
    # save_report_to_file should drop a YYYY-WW.md under output_dir.
    path = save_report_to_file(
        store, days=7, output_dir=str(tmp_path / "gap_reports")
    )
    written = Path(path)
    assert written.exists()
    assert written.name.endswith(".md")
    body = written.read_text(encoding="utf-8")
    assert "推奨アクション" in body
    assert "some unsatisfied topic" in body
