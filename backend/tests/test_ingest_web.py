"""Unit tests for ``backend.src.ingest_web`` (spec_046)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.src.ingest_web import _slugify, save_web_page


@pytest.fixture
def fixed_now() -> datetime:
    # 2026-05-20 12:34:56 UTC — keeps assertions deterministic.
    return datetime(2026, 5, 20, 12, 34, 56, tzinfo=UTC)


def test_save_creates_file_with_frontmatter(tmp_path: Path, fixed_now: datetime) -> None:
    path = save_web_page(
        url="https://example.com/post",
        title="Hello World",
        body="page body text",
        knowledge_dir=tmp_path,
        now=fixed_now,
    )
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    # YAML frontmatter delimited and includes the canonical fields.
    assert text.startswith("---\n")
    assert "\n---\n" in text
    assert "title: Hello World" in text
    assert "source: browser-extension" in text
    assert "url: https://example.com/post" in text
    assert "captured_at: 2026-05-20T12:34:56" in text
    # Body content follows the frontmatter.
    assert "# Hello World" in text
    assert "page body text" in text


def test_slugify_japanese_title() -> None:
    # NFKC folds wide ASCII ("Ｗｅｂ" → "Web") while letting kana / kanji
    # survive via Python's Unicode-aware \w.
    assert _slugify("Ｗｅｂ 記事 サンプル") == "web-記事-サンプル"
    # Plain ASCII keeps its words joined by '-'; the em-dash is stripped.
    assert _slugify("Hello World — A Test") == "hello-world-a-test"
    # Empty input falls back to the literal "web" sentinel.
    assert _slugify("") == "web"
    # Hyphens/spaces collapse, edge dashes stripped.
    assert _slugify("---foo  bar---") == "foo-bar"


def test_filename_includes_date(tmp_path: Path, fixed_now: datetime) -> None:
    path = save_web_page(
        url="https://example.com/x",
        title="Daily Notes 5/20",
        body="",
        knowledge_dir=tmp_path,
        now=fixed_now,
    )
    # web_YYYYMMDD_HHMMSS_<slug>.md
    assert path.name.startswith("web_20260520_123456_")
    assert path.suffix == ".md"


def test_selected_text_takes_priority_over_body(
    tmp_path: Path, fixed_now: datetime
) -> None:
    path = save_web_page(
        url="https://example.com/x",
        title="t",
        body="FULL BODY DUMP",
        selected_text="just-the-selection",
        knowledge_dir=tmp_path,
        now=fixed_now,
    )
    text = path.read_text(encoding="utf-8")
    assert "just-the-selection" in text
    assert "FULL BODY DUMP" not in text


def test_creates_knowledge_dir_if_missing(tmp_path: Path, fixed_now: datetime) -> None:
    target = tmp_path / "does" / "not" / "exist"
    assert not target.exists()
    path = save_web_page(
        url="https://example.com",
        title="title",
        body="body",
        knowledge_dir=target,
        now=fixed_now,
    )
    assert target.is_dir()
    assert path.parent == target


def test_axes_default_values(tmp_path: Path, fixed_now: datetime) -> None:
    path = save_web_page(
        url="https://example.com",
        title="title",
        body="body",
        knowledge_dir=tmp_path,
        now=fixed_now,
    )
    text = path.read_text(encoding="utf-8")
    # axes block written as a YAML mapping.
    assert "axes:" in text
    assert "  category: Web" in text
    assert "  topic: 未分類" in text
    assert "  level: 中級" in text


def test_refs_empty_list(tmp_path: Path, fixed_now: datetime) -> None:
    path = save_web_page(
        url="https://example.com",
        title="title",
        body="body",
        knowledge_dir=tmp_path,
        now=fixed_now,
    )
    text = path.read_text(encoding="utf-8")
    # Inline-empty list is the simplest YAML form for refs:[].
    assert "refs: []" in text


def test_url_preserved_in_frontmatter(tmp_path: Path, fixed_now: datetime) -> None:
    # Use a plain ASCII URL — `?` / `#` are still YAML-safe in our scalar
    # rendering since they don't appear in the disallow set unless leading.
    url = "https://example.com/path?q=1&hl=ja"
    path = save_web_page(
        url=url,
        title="title",
        body="body",
        knowledge_dir=tmp_path,
        now=fixed_now,
    )
    text = path.read_text(encoding="utf-8")
    # URL appears verbatim in both the frontmatter and the body source line.
    assert f"url: {url}" in text
    assert f"source: {url}" in text
