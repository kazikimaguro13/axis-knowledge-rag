"""Smoke tests for loader. Run via: python -m backend.tests.test_loader"""

import sys
import tempfile
from pathlib import Path

from backend.src.loader import LoaderError, load_directory, load_document


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_load_minimal_document() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.md"
        _write(
            p,
            """---
id: t1
title: Test 1
axes:
  category: 技術記事
tags: [a, b]
refs: []
---

Body text.
""",
        )
        doc = load_document(p)
        assert doc.id == "t1"
        assert doc.title == "Test 1"
        assert doc.axes == {"category": "技術記事"}
        assert doc.tags == ["a", "b"]
        assert "Body text." in doc.body


def test_missing_id_raises() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "bad.md"
        _write(p, "---\ntitle: no id\n---\nbody\n")
        try:
            load_document(p)
        except LoaderError:
            return
        raise AssertionError("LoaderError not raised")


def test_load_directory_skips_bad_files() -> None:
    with tempfile.TemporaryDirectory() as td:
        good = Path(td) / "good.md"
        bad = Path(td) / "bad.md"
        _write(good, "---\nid: g\ntitle: Good\n---\nok\n")
        _write(bad, "---\ntitle: no id\n---\nbody\n")
        docs = load_directory(Path(td))
        assert len(docs) == 1
        assert docs[0].id == "g"


def test_strict_mode_raises_on_bad_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        _write(Path(td) / "bad.md", "---\ntitle: no id\n---\nbody\n")
        try:
            load_directory(Path(td), strict=True)
        except LoaderError:
            return
        raise AssertionError("LoaderError not raised in strict mode")


if __name__ == "__main__":
    tests = [
        test_load_minimal_document,
        test_missing_id_raises,
        test_load_directory_skips_bad_files,
        test_strict_mode_raises_on_bad_file,
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
