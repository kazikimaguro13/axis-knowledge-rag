"""Tests for backend.src.live_ingest — single-file ingest pipeline (spec_056)."""

from pathlib import Path

import pytest

from backend.src.embedder import DummyEmbedder
from backend.src.live_ingest import ingest_file
from backend.src.normalizer import Normalizer
from backend.src.vector_store import VectorStore


def _write_memo(dir_path: Path, doc_id: str, body: str) -> Path:
    path = dir_path / f"{doc_id}.md"
    path.write_text(
        f"---\nid: {doc_id}\ntitle: Memo {doc_id}\n"
        f"axes:\n  category: メモ\n  topic: テスト\nrefs: []\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def test_ingest_file_indexes_chunks(tmp_path: Path) -> None:
    store = VectorStore(path=tmp_path / "chroma")
    embedder = DummyEmbedder()
    normalizer = Normalizer.identity()
    kdir = tmp_path / "kb"
    kdir.mkdir()
    path = _write_memo(kdir, "memo_001", "## H\n\nfirst paragraph.\n\nsecond paragraph.\n")

    result = ingest_file(path, store=store, embedder=embedder, normalizer=normalizer)

    assert result.doc_id == "memo_001"
    assert result.parents >= 1
    assert result.children >= 1
    assert store.count() == result.children


def test_ingest_file_reingest_is_upsert(tmp_path: Path) -> None:
    """Re-ingest with the same id must not crash with DuplicateIDError nor double the row count."""
    store = VectorStore(path=tmp_path / "chroma")
    embedder = DummyEmbedder()
    normalizer = Normalizer.identity()
    kdir = tmp_path / "kb"
    kdir.mkdir()
    path = _write_memo(kdir, "memo_dup", "## H\n\nbody.\n")

    first = ingest_file(path, store=store, embedder=embedder, normalizer=normalizer)
    second = ingest_file(path, store=store, embedder=embedder, normalizer=normalizer)

    assert second.deleted_existing == first.children
    assert store.count() == first.children


def test_ingest_file_updates_body(tmp_path: Path) -> None:
    """If the file's body changes between ingests, the new content wins."""
    store = VectorStore(path=tmp_path / "chroma")
    embedder = DummyEmbedder()
    normalizer = Normalizer.identity()
    kdir = tmp_path / "kb"
    kdir.mkdir()
    path = _write_memo(kdir, "memo_edit", "## H\n\noriginal text.\n")
    ingest_file(path, store=store, embedder=embedder, normalizer=normalizer)

    # Edit the file in-place
    path.write_text(
        "---\nid: memo_edit\ntitle: Memo memo_edit\n"
        "axes:\n  category: メモ\n  topic: テスト\nrefs: []\n---\n\n## H\n\nUPDATED text.\n",
        encoding="utf-8",
    )
    ingest_file(path, store=store, embedder=embedder, normalizer=normalizer)

    fresh = VectorStore(path=tmp_path / "chroma")
    fresh.load_parents()
    parent = next(iter(fresh.parents.values()))
    assert "UPDATED" in parent.text


def test_ingest_file_unknown_path_raises(tmp_path: Path) -> None:
    from backend.src.loader import LoaderError

    store = VectorStore(path=tmp_path / "chroma")
    embedder = DummyEmbedder()
    normalizer = Normalizer.identity()
    with pytest.raises(LoaderError):
        ingest_file(
            tmp_path / "does-not-exist.md",
            store=store,
            embedder=embedder,
            normalizer=normalizer,
        )
