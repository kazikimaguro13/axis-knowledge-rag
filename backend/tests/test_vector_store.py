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


# ---------------------------------------------------------------------------
# spec_026: list_with_filter / count_with_filter — pagination above 200
# ---------------------------------------------------------------------------


def test_count_with_filter_no_filter(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    docs = [_make_doc(f"d_{i:03d}") for i in range(5)]
    embeddings = dummy_embedder.embed_batch([d.body for d in docs])
    in_memory_store.upsert_many(docs, embeddings)
    assert in_memory_store.count_with_filter() == 5


def test_list_with_filter_pagination_above_200(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    """Verify the 200-row top_k limit is gone: paginate beyond row 200."""
    docs = [_make_doc(f"d_{i:04d}") for i in range(250)]
    embeddings = dummy_embedder.embed_batch([d.body for d in docs])
    in_memory_store.upsert_many(docs, embeddings)

    assert in_memory_store.count_with_filter() == 250

    page = in_memory_store.list_with_filter(limit=50, offset=200)
    assert len(page["ids"]) == 50
    # offset=200 + count=50 = 250 → we hit the last row of the dataset.

    last_page = in_memory_store.list_with_filter(limit=50, offset=240)
    assert len(last_page["ids"]) == 10


def test_list_and_count_with_filter_by_axis(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    d_a = Document(
        id="d_a",
        title="A",
        axes={"category": "alpha"},
        tags=[],
        refs=[],
        body="body a",
        path=Path("/tmp/a.md"),
        raw_meta={},
        normalized_axes={"category": "alpha"},
    )
    d_b = Document(
        id="d_b",
        title="B",
        axes={"category": "beta"},
        tags=[],
        refs=[],
        body="body b",
        path=Path("/tmp/b.md"),
        raw_meta={},
        normalized_axes={"category": "beta"},
    )
    in_memory_store.upsert(d_a, dummy_embedder.embed(d_a.body))
    in_memory_store.upsert(d_b, dummy_embedder.embed(d_b.body))

    where = {"axis_category_norm": "alpha"}
    assert in_memory_store.count_with_filter(where) == 1
    page = in_memory_store.list_with_filter(where=where, limit=10, offset=0)
    assert page["ids"] == ["d_a"]
