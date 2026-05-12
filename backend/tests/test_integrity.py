"""Tests for IntegrityChecker. Run via: python -m backend.tests.test_integrity"""

import sys
import tempfile
from pathlib import Path

from backend.src.integrity import IntegrityChecker
from backend.src.loader import Document


def _doc(doc_id: str, refs: list[str] | None = None) -> Document:
    return Document(
        id=doc_id,
        title=f"Title {doc_id}",
        axes={},
        tags=[],
        refs=refs or [],
        body="body",
        path=Path(f"/fake/{doc_id}.md"),
    )


def test_no_broken_refs() -> None:
    docs = [
        _doc("doc_001", refs=["doc_002"]),
        _doc("doc_002", refs=["doc_003"]),
        _doc("doc_003"),
        _doc("doc_004"),
        _doc("doc_005"),
    ]
    report = IntegrityChecker().check(docs)
    assert report.total_docs == 5
    assert report.total_refs == 2
    assert report.has_errors is False
    assert report.broken_refs == []


def test_broken_ref_detected() -> None:
    docs = [
        _doc("doc_001", refs=["doc_999"]),
        _doc("doc_002"),
    ]
    report = IntegrityChecker().check(docs)
    assert report.has_errors is True
    assert len(report.broken_refs) == 1
    br = report.broken_refs[0]
    assert br.source_id == "doc_001"
    assert br.target_id == "doc_999"


def test_orphan_doc_detected() -> None:
    # doc_001 is not referenced by anyone
    docs = [
        _doc("doc_001"),
        _doc("doc_002", refs=["doc_003"]),
        _doc("doc_003"),
    ]
    report = IntegrityChecker().check(docs)
    assert "doc_001" in report.orphan_docs
    # doc_002 also not referenced; doc_003 is referenced by doc_002
    assert "doc_002" in report.orphan_docs
    assert "doc_003" not in report.orphan_docs


def test_cycle_detected() -> None:
    # A -> B -> A (simple 2-node cycle)
    docs = [
        _doc("A", refs=["B"]),
        _doc("B", refs=["A"]),
    ]
    report = IntegrityChecker().check(docs)
    assert len(report.cycles) >= 1
    # Every node in cycles should be from [A, B]
    for cycle in report.cycles:
        for node in cycle:
            assert node in ("A", "B")


def test_self_loop_detected() -> None:
    # A -> A (self-reference is a cycle of length 1)
    docs = [
        _doc("A", refs=["A"]),
        _doc("B"),
    ]
    report = IntegrityChecker().check(docs)
    assert len(report.cycles) >= 1
    found_self = any("A" in cycle and cycle.count("A") >= 2 for cycle in report.cycles)
    assert found_self, f"Expected self-loop in cycles, got: {report.cycles}"


if __name__ == "__main__":
    tests = [
        test_no_broken_refs,
        test_broken_ref_detected,
        test_orphan_doc_detected,
        test_cycle_detected,
        test_self_loop_detected,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            print(f"FAIL: {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    sys.exit(1 if failed else 0)
