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


# ---------------------------------------------------------------------------
# spec_031: parent-document retrieval (add_chunks / query_with_parents)
# ---------------------------------------------------------------------------


def test_add_chunks_persists_parents_and_embeds_children(
    tmp_path: Path, dummy_embedder: Embedder
) -> None:
    from backend.src.chunker import chunk_markdown

    store = VectorStore(path=tmp_path / "chroma")
    body = (
        "## Alpha\n\nFirst paragraph.\n\n## Beta\n\nSecond paragraph.\n\n"
        "Another sentence in beta.\n"
    )
    parents, children = chunk_markdown(
        "kb/sample.md", body, {"title": "Sample"}, max_child_tokens=64
    )
    embeddings = dummy_embedder.embed_batch([c.text for c in children])
    store.add_chunks(parents, children, embeddings)

    assert store.count() == len(children)
    assert (tmp_path / "chroma" / "parents.db").exists()  # spec_037: SQLite default


def test_query_with_parents_groups_children_to_top_n(
    tmp_path: Path, dummy_embedder: Embedder
) -> None:
    from backend.src.chunker import chunk_markdown

    store = VectorStore(path=tmp_path / "chroma")
    parents_all: list = []
    children_all: list = []
    for i, body in enumerate([
        "## Alpha\n\nfirst body of alpha doc.\n",
        "## Beta\n\nsecond body of beta doc.\n",
        "## Gamma\n\nthird body of gamma doc.\n",
    ]):
        ps, cs = chunk_markdown(f"kb/{i}.md", body, {"title": f"D{i}"})
        parents_all.extend(ps)
        children_all.extend(cs)
    embeddings = dummy_embedder.embed_batch([c.text for c in children_all])
    store.add_chunks(parents_all, children_all, embeddings)

    q = dummy_embedder.embed("first body of alpha doc.")
    results = store.query_with_parents(q, top_k_children=10, top_n_parents=2)
    assert len(results) == 2
    for parent, score in results:
        assert parent.parent_id.startswith("kb/")
        assert 0.0 <= score <= 1.0


def test_load_parents_reads_sidecar(tmp_path: Path, dummy_embedder: Embedder) -> None:
    from backend.src.chunker import chunk_markdown

    db_dir = tmp_path / "chroma"
    store = VectorStore(path=db_dir)
    parents, children = chunk_markdown(
        "kb/x.md", "## H\n\nbody.", {"title": "X"}
    )
    embeddings = dummy_embedder.embed_batch([c.text for c in children])
    store.add_chunks(parents, children, embeddings)

    # Re-open: the in-memory parents cache starts empty; SQLite has the data.
    fresh = VectorStore(path=db_dir)
    assert fresh.parents == {}
    assert fresh.has_parents() is True  # storage has data
    n = fresh.load_parents()            # populate cache from SQLite
    assert n == 1
    assert next(iter(fresh.parents.values())).title == "H"


def test_add_chunks_length_mismatch_raises(
    tmp_path: Path, dummy_embedder: Embedder
) -> None:
    from backend.src.chunker import chunk_markdown

    store = VectorStore(path=tmp_path / "chroma")
    parents, children = chunk_markdown("kb/d.md", "## A\n\nbody.", {})
    with pytest.raises(ValueError):
        store.add_chunks(parents, children, [])


def test_reset_clears_parents_sidecar(
    tmp_path: Path, dummy_embedder: Embedder
) -> None:
    from backend.src.chunker import chunk_markdown

    db_dir = tmp_path / "chroma"
    store = VectorStore(path=db_dir)
    parents, children = chunk_markdown("kb/r.md", "## R\n\nbody.", {})
    embeddings = dummy_embedder.embed_batch([c.text for c in children])
    store.add_chunks(parents, children, embeddings)
    assert (db_dir / "parents.db").exists()  # spec_037: SQLite default
    store.reset()
    assert not store.has_parents()           # storage cleared
    assert store.parents == {}


# ---------------------------------------------------------------------------
# spec_037: SQLite storage path tests (3 tests)
# ---------------------------------------------------------------------------


def test_sqlite_has_parents_true_after_add(
    tmp_path: Path, dummy_embedder: Embedder
) -> None:
    """has_parents() reflects SQLite state even on a fresh VectorStore instance."""
    from backend.src.chunker import chunk_markdown

    db_dir = tmp_path / "chroma"
    store = VectorStore(path=db_dir)
    parents, children = chunk_markdown("kb/s.md", "## S\n\nbody.", {})
    embeddings = dummy_embedder.embed_batch([c.text for c in children])
    store.add_chunks(parents, children, embeddings)

    fresh = VectorStore(path=db_dir)
    assert fresh.has_parents() is True
    assert fresh.parents == {}  # cache not yet populated


def test_sqlite_load_parents_returns_correct_count(
    tmp_path: Path, dummy_embedder: Embedder
) -> None:
    """load_parents() returns the number of parents loaded from SQLite."""
    from backend.src.chunker import chunk_markdown

    db_dir = tmp_path / "chroma"
    store = VectorStore(path=db_dir)
    for i in range(3):
        parents, children = chunk_markdown(
            f"kb/doc{i}.md", f"## Section {i}\n\nparagraph {i}.", {}
        )
        embeddings = dummy_embedder.embed_batch([c.text for c in children])
        store.add_chunks(parents, children, embeddings)

    fresh = VectorStore(path=db_dir)
    n = fresh.load_parents()
    assert n == 3


def test_sqlite_has_parents_false_after_reset(
    tmp_path: Path, dummy_embedder: Embedder
) -> None:
    """has_parents() returns False after reset(), even though parents.db file remains."""
    from backend.src.chunker import chunk_markdown

    db_dir = tmp_path / "chroma"
    store = VectorStore(path=db_dir)
    parents, children = chunk_markdown("kb/t.md", "## T\n\nbody.", {})
    embeddings = dummy_embedder.embed_batch([c.text for c in children])
    store.add_chunks(parents, children, embeddings)
    assert store.has_parents() is True

    store.reset()
    assert store.has_parents() is False
