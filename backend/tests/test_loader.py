"""Smoke tests for loader."""

import tempfile
from pathlib import Path

import pytest

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
        with pytest.raises(LoaderError):
            load_document(p)


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
        with pytest.raises(LoaderError):
            load_directory(Path(td), strict=True)
