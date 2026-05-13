"""Smoke tests for vector_store."""

from pathlib import Path

import pytest

from backend.src.embedder import Embedder
from backend.src.loader import Document
from backend.src.vector_store import VectorStore


def _make_doc(doc_id: str, body: str = "body text") -> Document:
    return Document(
        id=doc_id,
        title=f"Title {doc_id}",
        axes={"category": "test", "level": "beginner"},
        tags=["a", "b"],
        refs=[],
        body=body,
        path=Path(f"/tmp/{doc_id}.md"),
        raw_meta={},
    )


def test_upsert_increments_count(in_memory_store: VectorStore, dummy_embedder: Embedder) -> None:
    doc = _make_doc("d1")
    in_memory_store.upsert(doc, dummy_embedder.embed(doc.body))
    assert in_memory_store.count() == 1


def test_upsert_many_and_query_returns_results(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    docs = [_make_doc(f"d{i}", body=f"body {i}") for i in range(3)]
    embeddings = dummy_embedder.embed_batch([d.body for d in docs])
    in_memory_store.upsert_many(docs, embeddings)
    assert in_memory_store.count() == 3

    q = dummy_embedder.embed("body 0")
    result = in_memory_store.query(q, n_results=2)
    assert "ids" in result
    assert len(result["ids"][0]) == 2


def test_reset_clears_collection(in_memory_store: VectorStore, dummy_embedder: Embedder) -> None:
    doc = _make_doc("d1")
    in_memory_store.upsert(doc, dummy_embedder.embed(doc.body))
    assert in_memory_store.count() == 1
    in_memory_store.reset()
    assert in_memory_store.count() == 0


def test_upsert_many_length_mismatch_raises(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    docs = [_make_doc("d1"), _make_doc("d2")]
    embeddings = [dummy_embedder.embed("only one")]
    with pytest.raises(ValueError):
        in_memory_store.upsert_many(docs, embeddings)


def test_axis_filter_query(in_memory_store: VectorStore, dummy_embedder: Embedder) -> None:
    d_test = _make_doc("d_test")
    d_other = Document(
        id="d_other",
        title="Other",
        axes={"category": "other"},
        tags=[],
        refs=[],
        body="different body",
        path=Path("/tmp/d_other.md"),
        raw_meta={},
    )
    in_memory_store.upsert(d_test, dummy_embedder.embed(d_test.body))
    in_memory_store.upsert(d_other, dummy_embedder.embed(d_other.body))
    result = in_memory_store.query(
        dummy_embedder.embed("query"), n_results=5, where={"axis_category": "test"}
    )
    assert result["ids"][0] == ["d_test"]
