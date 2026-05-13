"""Integration tests for SearchEngine."""

from pathlib import Path

import pytest

from backend.src.bm25_index import BM25Index
from backend.src.embedder import Embedder
from backend.src.loader import Document
from backend.src.normalizer import Normalizer, normalize_text
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


# ---------------------------------------------------------------------------
# spec_029: BM25 fusion
# ---------------------------------------------------------------------------


@pytest.fixture
def bm25_engine(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> tuple[SearchEngine, SearchEngine]:
    """Return (engine_without_bm25, engine_with_bm25) sharing the same corpus.

    Bodies are crafted so BM25 (keyword match) and dummy embeddings (hash-derived,
    semantically meaningless) produce different orderings — that's exactly the
    scenario we want to assert.
    """
    docs = [
        _make_doc("chroma", "技術記事", "chromadb の永続化設計について書いたメモ"),
        _make_doc("fastapi", "技術記事", "fastapi で軸検索 api を作る話"),
        _make_doc("rag",    "技術記事", "rag パイプラインの設計判断"),
        _make_doc("meeting", "メモ",     "今日の会議メモ プロジェクト進捗確認"),
    ]
    embeddings = dummy_embedder.embed_batch([d.body for d in docs])
    in_memory_store.upsert_many(docs, embeddings)

    plain = SearchEngine(in_memory_store, dummy_embedder, Normalizer())
    bm25 = BM25Index.build(
        [(d.id, normalize_text(d.body)) for d in docs], Normalizer()
    )
    fused = SearchEngine(in_memory_store, dummy_embedder, Normalizer(), bm25_index=bm25)
    return plain, fused


def test_search_bm25_weight_0_matches_vector_only(
    bm25_engine: tuple[SearchEngine, SearchEngine],
) -> None:
    """bm25_weight=0.0 must reproduce the v0.5 vector-only ranking exactly."""
    plain, fused = bm25_engine

    plain_results = plain.search("chromadb", top_k=4)
    fused_results = fused.search("chromadb", top_k=4, bm25_weight=0.0)

    assert [r.id for r in plain_results] == [r.id for r in fused_results]
    for p, f in zip(plain_results, fused_results, strict=True):
        assert p.score == pytest.approx(f.score)


def test_search_bm25_weight_1_orders_by_keyword_match(
    bm25_engine: tuple[SearchEngine, SearchEngine],
) -> None:
    """bm25_weight=1.0 ranks by BM25 alone — the keyword-matching doc tops."""
    _, fused = bm25_engine
    results = fused.search("chromadb", top_k=4, bm25_weight=1.0)
    assert results[0].id == "chroma"


def test_search_bm25_changes_ranking(
    bm25_engine: tuple[SearchEngine, SearchEngine],
) -> None:
    """Vector-only and 50/50 fusion must produce a different top result for a
    query that BM25 can latch onto but the dummy embedding cannot."""
    _, fused = bm25_engine

    vec_only = fused.search("chromadb", top_k=4, bm25_weight=0.0)
    fused_05 = fused.search("chromadb", top_k=4, bm25_weight=0.5)

    # Either the order changes, or the top doc is now the BM25 match.
    assert (
        [r.id for r in vec_only] != [r.id for r in fused_05]
        or fused_05[0].id == "chroma"
    )
    # 50/50 fusion should at least pull the keyword match into the top result.
    assert fused_05[0].id == "chroma"


def test_search_bm25_weight_ignored_when_no_index(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    """An engine without a BM25 index must behave identically regardless of
    bm25_weight (graceful no-op rather than error)."""
    docs = [
        _make_doc("d1", "技術記事", "RAGとはRetrieval-Augmented Generation"),
        _make_doc("d2", "技術記事", "ベクトル検索とコサイン類似度"),
    ]
    embeddings = dummy_embedder.embed_batch([d.body for d in docs])
    in_memory_store.upsert_many(docs, embeddings)

    engine = SearchEngine(in_memory_store, dummy_embedder)  # no bm25_index
    r1 = engine.search("RAGとは", top_k=2, bm25_weight=0.0)
    r2 = engine.search("RAGとは", top_k=2, bm25_weight=0.8)
    assert [r.id for r in r1] == [r.id for r in r2]


def test_search_axis_only_ignores_bm25(
    bm25_engine: tuple[SearchEngine, SearchEngine],
) -> None:
    """query=None (axis-only) must short-circuit BM25 — there is no query to
    score against."""
    _, fused = bm25_engine
    results = fused.search(None, filters={"category": "メモ"}, top_k=5, bm25_weight=1.0)
    assert len(results) == 1
    assert results[0].id == "meeting"
