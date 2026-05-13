"""Integration tests for SearchEngine."""

from pathlib import Path

import pytest

from backend.src.embedder import Embedder
from backend.src.loader import Document
from backend.src.normalizer import normalize_text
from backend.src.search import SearchEngine, SearchResult, _build_where
from backend.src.vector_store import VectorStore


def _make_doc(doc_id: str, category: str, body: str) -> Document:
    axes = {"category": category}
    return Document(
        id=doc_id,
        title=f"Doc {doc_id}",
        axes=axes,
        tags=[],
        refs=[],
        body=body,
        path=Path(f"/tmp/{doc_id}.md"),
        raw_meta={},
        normalized_title=normalize_text(f"Doc {doc_id}"),
        normalized_body=normalize_text(body),
        normalized_axes={k: normalize_text(str(v)) for k, v in axes.items()},
        normalized_tags=[],
    )



@pytest.fixture
def loaded_engine(in_memory_store: VectorStore, dummy_embedder: Embedder) -> SearchEngine:
    docs = [
        _make_doc("d1", "技術記事", "RAGとはRetrieval-Augmented Generationの略です"),
        _make_doc("d2", "技術記事", "ベクトル検索はコサイン類似度を用います"),
        _make_doc("d3", "メモ", "今日の会議メモ: プロジェクト進捗確認"),
    ]
    embeddings = dummy_embedder.embed_batch([d.body for d in docs])
    in_memory_store.upsert_many(docs, embeddings)
    return SearchEngine(in_memory_store, dummy_embedder)


def test_query_no_filter_returns_all(loaded_engine: SearchEngine) -> None:
    results = loaded_engine.search("RAGとは", top_k=10)
    assert len(results) == 3


def test_query_with_category_filter(loaded_engine: SearchEngine) -> None:
    results = loaded_engine.search("RAGとは", filters={"category": "技術記事"}, top_k=10)
    assert len(results) == 2
    for r in results:
        assert r.axes.get("category") == "技術記事"


def test_axis_only_no_query_with_filter(loaded_engine: SearchEngine) -> None:
    results = loaded_engine.search(None, filters={"category": "メモ"}, top_k=10)
    assert len(results) == 1
    assert results[0].id == "d3"


def test_score_in_range(loaded_engine: SearchEngine) -> None:
    results = loaded_engine.search("RAGとは", top_k=10)
    for r in results:
        assert 0.0 <= r.score <= 1.0


def test_result_has_required_fields(loaded_engine: SearchEngine) -> None:
    results = loaded_engine.search("RAGとは", top_k=1)
    assert results
    r = results[0]
    assert isinstance(r, SearchResult)
    assert r.id
    assert isinstance(r.title, str)
    assert isinstance(r.score, float)
    assert isinstance(r.axes, dict)
    assert isinstance(r.body_snippet, str)
    assert isinstance(r.path, str)
    assert isinstance(r.refs, list)


@pytest.mark.parametrize(
    "filters,expected",
    [
        ({"category": "技術記事"}, {"axis_category": "技術記事"}),
    ],
)
def test_build_where_single_key(filters: dict, expected: dict) -> None:
    assert _build_where(filters) == expected


def test_build_where_multi_key() -> None:
    w = _build_where({"category": "技術記事", "level": "中級"})
    assert w is not None
    assert "$and" in w
    items = w["$and"]
    assert {"axis_category": "技術記事"} in items
    assert {"axis_level": "中級"} in items


def test_build_where_empty_returns_none() -> None:
    assert _build_where({}) is None
