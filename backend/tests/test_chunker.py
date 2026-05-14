"""Unit tests for the parent-child Markdown chunker (spec_031)."""

from __future__ import annotations

from backend.src.chunker import (
    DEFAULT_MAX_CHILD_TOKENS,
    ChildChunk,
    ParentChunk,
    chunk_markdown,
)


def test_chunk_no_h2_returns_single_parent() -> None:
    """A doc with no H2 heading must collapse into one root parent."""
    body = "This is a body without any H2 heading.\n\nIt has two paragraphs."
    parents, children = chunk_markdown("knowledge/x.md", body, {"title": "Doc X"})
    assert len(parents) == 1
    assert parents[0].title == "Doc X"
    assert parents[0].parent_id == "knowledge/x.md#doc-x"
    assert parents[0].doc_id == "knowledge/x.md"
    assert len(children) >= 1
    for c in children:
        assert c.parent_id == parents[0].parent_id


def test_chunk_with_h2_splits_correctly() -> None:
    body = (
        "Preamble paragraph.\n\n"
        "## Section One\n\n"
        "First section body.\n\n"
        "## Section Two\n\n"
        "Second body.\n\n"
        "## Section Three\n\n"
        "Third."
    )
    parents, _ = chunk_markdown("kb/three.md", body, {"title": "Three"})
    # Three H2 sections + one root parent for the preamble
    assert [p.title for p in parents] == ["Three", "Section One", "Section Two", "Section Three"]


def test_chunk_with_h2_no_preamble() -> None:
    """If the doc starts directly with an H2, no synthetic root parent is created."""
    body = "## Only Section\n\nBody.\n"
    parents, children = chunk_markdown("kb/one.md", body, {"title": "T"})
    assert len(parents) == 1
    assert parents[0].title == "Only Section"
    assert children and children[0].text == "Body."


def test_child_token_cap() -> None:
    """A long single paragraph must be broken into multiple children."""
    long_text = ("これはとても長い文章。" * 200).strip()
    body = f"## Long\n\n{long_text}\n"
    _, children = chunk_markdown("kb/long.md", body, {}, max_child_tokens=64)
    assert len(children) >= 2
    char_cap = 64 * 2
    # Allow some slack: greedy sentence merging may slightly exceed by 1 sentence
    for c in children:
        assert len(c.text) <= char_cap + len("これはとても長い文章。")


def test_child_boundary_respects_sentence_end() -> None:
    """Children must not split mid-sentence; every chunk should end at 。 or .
    (unless a single sentence itself exceeds the cap).
    """
    body = "## S\n\n" + "あいうえお。" * 100 + "\n"
    _, children = chunk_markdown("kb/sent.md", body, {}, max_child_tokens=32)
    assert len(children) >= 2
    for c in children:
        assert c.text.endswith("。"), f"chunk does not end at sentence boundary: {c.text!r}"


def test_parent_text_reconstruction_contains_children() -> None:
    """Every child's text must appear as a substring of its parent's text."""
    body = (
        "## Alpha\n\n"
        "First paragraph.\n\n"
        "Second paragraph.\n\n"
        "### Sub\n\n"
        "Sub body."
    )
    parents, children = chunk_markdown("kb/a.md", body, {})
    by_parent = {p.parent_id: p for p in parents}
    for c in children:
        assert c.parent_id in by_parent
        assert c.text.strip() in by_parent[c.parent_id].text


def test_parent_id_deterministic() -> None:
    body = "## My Section\n\nBody."
    p1, _ = chunk_markdown("kb/d.md", body, {})
    p2, _ = chunk_markdown("kb/d.md", body, {})
    assert p1[0].parent_id == p2[0].parent_id


def test_orphan_child_never_generated() -> None:
    body = (
        "## A\n\nbody A\n\n"
        "## B\n\nbody B\n\n"
        "## C\n\nbody C\n"
    )
    parents, children = chunk_markdown("kb/multi.md", body, {})
    pids = {p.parent_id for p in parents}
    for c in children:
        assert c.parent_id in pids


def test_empty_body_returns_empty() -> None:
    parents, children = chunk_markdown("kb/e.md", "", {"title": "Empty"})
    assert parents == []
    assert children == []


def test_metadata_inherited_by_children() -> None:
    fm = {"title": "T", "axes": {"category": "技術記事"}, "year": 2026}
    body = "## S\n\nbody."
    parents, children = chunk_markdown("kb/m.md", body, fm)
    assert parents[0].metadata == fm
    assert children[0].metadata == fm


def test_cjk_only_title_falls_back_to_hash_slug() -> None:
    """A CJK-only H2 title must still produce a stable, ASCII-safe parent id."""
    body = "## 日本語見出し\n\n本文。"
    parents, _ = chunk_markdown("kb/jp.md", body, {})
    pid = parents[0].parent_id
    assert pid.startswith("kb/jp.md#")
    suffix = pid.split("#", 1)[1]
    # 8-char md5 hex slug
    assert len(suffix) == 8
    assert all(ch in "0123456789abcdef" for ch in suffix)
    # Determinism
    parents2, _ = chunk_markdown("kb/jp.md", body, {})
    assert parents[0].parent_id == parents2[0].parent_id


def test_heading_only_section_emits_parent_with_no_children() -> None:
    body = "## Empty Section\n\n## Real\n\nbody."
    parents, children = chunk_markdown("kb/h.md", body, {})
    titles = [p.title for p in parents]
    assert "Empty Section" in titles
    empty_pid = next(p.parent_id for p in parents if p.title == "Empty Section")
    assert all(c.parent_id != empty_pid for c in children)


def test_dataclasses_are_frozen() -> None:
    from dataclasses import FrozenInstanceError

    import pytest

    body = "## S\n\nbody."
    parents, children = chunk_markdown("kb/f.md", body, {})
    assert isinstance(parents[0], ParentChunk)
    assert isinstance(children[0], ChildChunk)

    with pytest.raises(FrozenInstanceError):
        parents[0].title = "mutated"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        children[0].text = "mutated"  # type: ignore[misc]


def test_default_max_child_tokens_constant() -> None:
    assert DEFAULT_MAX_CHILD_TOKENS == 256
