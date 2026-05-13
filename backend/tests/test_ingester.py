"""Tests for backend.src.ingester (DUMMY mode only — no API key required)."""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from backend.src.ingester import (
    Ingester,
    _next_doc_id,
    _strip_code_fence,
    render_markdown,
)
from backend.src.ingester_schemas import IngestOptions, IngestResult


@pytest.fixture
def empty_knowledge_dir(tmp_path: Path) -> Path:
    d = tmp_path / "knowledge_empty"
    d.mkdir()
    return d


@pytest.fixture
def populated_knowledge_dir(tmp_path: Path) -> Path:
    d = tmp_path / "knowledge_pop"
    d.mkdir()
    for n in range(1, 11):  # doc_001 .. doc_010
        (d / f"doc_{n:03d}.md").write_text(
            f"---\nid: doc_{n:03d}\ntitle: Existing {n}\naxes:\n  category: メモ\nrefs: []\n---\nBody {n}.\n",
            encoding="utf-8",
        )
    return d


def test_next_doc_id_empty_dir(empty_knowledge_dir: Path) -> None:
    assert _next_doc_id(empty_knowledge_dir) == "doc_001"


def test_next_doc_id_missing_dir(tmp_path: Path) -> None:
    assert _next_doc_id(tmp_path / "does_not_exist") == "doc_001"


def test_next_doc_id_increments(populated_knowledge_dir: Path) -> None:
    assert _next_doc_id(populated_knowledge_dir) == "doc_011"


def test_dummy_mode_produces_valid_result(empty_knowledge_dir: Path) -> None:
    ingester = Ingester(force_dummy=True)
    assert ingester.is_dummy is True
    opts = IngestOptions(knowledge_dir=str(empty_knowledge_dir))
    result = ingester.ingest("これはテスト用の生メモ本文です。ある程度の長さを持たせます。", opts)
    assert isinstance(result, IngestResult)
    assert result.id == "doc_001"
    assert len(result.body) >= 20
    assert "category" in result.axes


def test_dummy_mode_is_deterministic(empty_knowledge_dir: Path) -> None:
    ingester = Ingester(force_dummy=True)
    opts = IngestOptions(knowledge_dir=str(empty_knowledge_dir))
    raw = "決定論的なテキスト入力サンプル。同じ入力なら同じ出力になる。"
    a = ingester.ingest(raw, opts)
    b = ingester.ingest(raw, opts)
    assert a.title == b.title  # hash-derived → same input ⇒ same title


def test_render_markdown_round_trip(empty_knowledge_dir: Path) -> None:
    ingester = Ingester(force_dummy=True)
    opts = IngestOptions(knowledge_dir=str(empty_knowledge_dir))
    result = ingester.ingest("ラウンドトリップ用のサンプル本文を渡す。最低 20 文字。", opts)
    md = render_markdown(result)
    post = frontmatter.loads(md)
    assert post["id"] == result.id
    assert post["title"] == result.title
    assert dict(post["axes"]) == result.axes
    assert list(post["tags"]) == result.tags
    assert post.content.strip() == result.body.strip()


def test_render_markdown_starts_with_frontmatter(empty_knowledge_dir: Path) -> None:
    ingester = Ingester(force_dummy=True)
    opts = IngestOptions(knowledge_dir=str(empty_knowledge_dir))
    result = ingester.ingest("先頭が YAML frontmatter になっていることを確認するサンプル。", opts)
    md = render_markdown(result)
    assert md.startswith("---\n")
    assert "\n---\n\n" in md


def test_ingest_result_rejects_invalid_ref() -> None:
    with pytest.raises(ValueError):
        IngestResult(
            id="doc_999",
            title="title",
            axes={"category": "メモ"},
            tags=[],
            refs=["not_a_doc_id"],  # must start with doc_
            body="body content long enough to pass validation",
        )


def test_ingest_result_rejects_bad_id_pattern() -> None:
    with pytest.raises(ValueError):
        IngestResult(
            id="document_001",
            title="title",
            axes={"category": "メモ"},
            tags=[],
            refs=[],
            body="body content long enough to pass validation",
        )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("```json\n{\"a\":1}\n```", '{"a":1}'),
        ("```\n{\"a\":1}\n```", '{"a":1}'),
        ('{"a":1}', '{"a":1}'),
        ("  {\"a\":1}  ", '{"a":1}'),
    ],
)
def test_strip_code_fence(raw: str, expected: str) -> None:
    assert _strip_code_fence(raw) == expected
