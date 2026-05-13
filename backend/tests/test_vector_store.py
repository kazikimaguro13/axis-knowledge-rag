"""Smoke tests for vector_store. Run via: python -m backend.tests.test_vector_store"""

import sys
from pathlib import Path

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


def _fresh_store() -> VectorStore:
    # Chroma EphemeralClient はプロセス内で内部 system を共有するため、
    # 同一 COLLECTION_NAME を使うテストでは毎回 reset() で隔離する。
    s = VectorStore(in_memory=True)
    s.reset()
    return s


def test_upsert_increments_count() -> None:
    store = _fresh_store()
    embedder = Embedder(force_dummy=True)
    doc = _make_doc("d1")
    store.upsert(doc, embedder.embed(doc.body))
    assert store.count() == 1


def test_upsert_many_and_query_returns_results() -> None:
    store = _fresh_store()
    embedder = Embedder(force_dummy=True)
    docs = [_make_doc(f"d{i}", body=f"body {i}") for i in range(3)]
    embeddings = embedder.embed_batch([d.body for d in docs])
    store.upsert_many(docs, embeddings)
    assert store.count() == 3

    q = embedder.embed("body 0")
    result = store.query(q, n_results=2)
    assert "ids" in result
    assert len(result["ids"][0]) == 2


def test_reset_clears_collection() -> None:
    store = _fresh_store()
    embedder = Embedder(force_dummy=True)
    doc = _make_doc("d1")
    store.upsert(doc, embedder.embed(doc.body))
    assert store.count() == 1
    store.reset()
    assert store.count() == 0


def test_upsert_many_length_mismatch_raises() -> None:
    store = _fresh_store()
    embedder = Embedder(force_dummy=True)
    docs = [_make_doc("d1"), _make_doc("d2")]
    embeddings = [embedder.embed("only one")]
    try:
        store.upsert_many(docs, embeddings)
    except ValueError:
        return
    raise AssertionError("ValueError not raised for length mismatch")


def test_axis_filter_query() -> None:
    store = _fresh_store()
    embedder = Embedder(force_dummy=True)
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
    store.upsert(d_test, embedder.embed(d_test.body))
    store.upsert(d_other, embedder.embed(d_other.body))
    result = store.query(
        embedder.embed("query"), n_results=5, where={"axis_category": "test"}
    )
    assert result["ids"][0] == ["d_test"]


if __name__ == "__main__":
    tests = [
        test_upsert_increments_count,
        test_upsert_many_and_query_returns_results,
        test_reset_clears_collection,
        test_upsert_many_length_mismatch_raises,
        test_axis_filter_query,
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
