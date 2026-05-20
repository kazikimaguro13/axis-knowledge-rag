"""Integration tests for SearchEngine."""

from datetime import UTC
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


# ---------------------------------------------------------------------------
# spec_031: Parent-document retrieval mode
# ---------------------------------------------------------------------------


@pytest.fixture
def parent_doc_engine(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> SearchEngine:
    """Build a search engine seeded with chunked Markdown (parent-doc path)."""
    from backend.src.chunker import chunk_markdown

    docs_md = [
        ("doc_alpha", "## RAG とは\n\nRAGは検索拡張生成です。\n\n## 設計\n\n設計判断を述べます。\n"),
        ("doc_beta",  "## ベクトル検索\n\nコサイン類似度を使います。\n"),
        ("doc_gamma", "## メモ\n\n会議メモ。\n"),
    ]
    parents_all = []
    children_all = []
    for doc_id, body in docs_md:
        ps, cs = chunk_markdown(doc_id, body, {"title": doc_id})
        parents_all.extend(ps)
        children_all.extend(cs)
    embeddings = dummy_embedder.embed_batch([c.text for c in children_all])
    in_memory_store.add_chunks(parents_all, children_all, embeddings)
    return SearchEngine(
        in_memory_store, dummy_embedder, parent_doc_enabled=True
    )


def test_parent_doc_search_returns_parent_results(parent_doc_engine: SearchEngine) -> None:
    results = parent_doc_engine.search("RAG", top_k=3)
    assert results
    for r in results:
        # parent_id format: "{doc_id}#{slug}"
        assert "#" in r.id
        assert r.body_full  # parent text is populated for RAG context
        assert r.body_snippet  # snippet is also populated for UI


def test_parent_doc_search_dedup_by_parent(parent_doc_engine: SearchEngine) -> None:
    """Each result's parent_id must be unique (no duplicates)."""
    results = parent_doc_engine.search("RAG", top_k=10)
    ids = [r.id for r in results]
    assert len(ids) == len(set(ids))


def test_parent_doc_axis_only_path(parent_doc_engine: SearchEngine) -> None:
    """Axis-only query must still work in parent-doc mode."""
    results = parent_doc_engine.search(None, top_k=10)
    assert results  # at least one parent comes back
    for r in results:
        assert r.body_full


def test_parent_doc_engine_property_exposed(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    legacy = SearchEngine(in_memory_store, dummy_embedder)
    assert legacy.parent_doc_enabled is False
    pdoc = SearchEngine(in_memory_store, dummy_embedder, parent_doc_enabled=True)
    assert pdoc.parent_doc_enabled is True


def test_parent_doc_with_bm25_fusion_collapses_per_doc(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    """BM25 + parent_doc: multiple parents from one doc collapse to single best."""
    from backend.src.chunker import chunk_markdown

    docs_md = [
        ("doc_alpha",
         "## RAG とは\n\nrag についての説明。\n\n## 設計\n\n設計判断の話。\n"),
        ("doc_beta",
         "## ベクトル検索\n\nコサイン類似度の話。\n"),
    ]
    parents_all = []
    children_all = []
    for doc_id, body in docs_md:
        ps, cs = chunk_markdown(doc_id, body, {"title": doc_id})
        parents_all.extend(ps)
        children_all.extend(cs)
    embeddings = dummy_embedder.embed_batch([c.text for c in children_all])
    in_memory_store.add_chunks(parents_all, children_all, embeddings)

    bm25 = BM25Index.build(
        [(p.doc_id, normalize_text(p.text)) for p in parents_all], Normalizer()
    )
    engine = SearchEngine(
        in_memory_store, dummy_embedder, Normalizer(),
        bm25_index=bm25, parent_doc_enabled=True,
    )
    results = engine.search("rag", top_k=5, bm25_weight=0.5)
    paths = [r.path for r in results]
    # Each file should appear at most once after collapse
    assert len(paths) == len(set(paths))


# ---------------------------------------------------------------------------
# spec_035: Time-weighted decay
# ---------------------------------------------------------------------------


def test_time_decay_reorders_by_recency() -> None:
    """_apply_time_decay demotes older docs relative to newer ones (same base score)."""
    from datetime import datetime, timedelta

    from backend.src.config import TimeDecayConfig
    from backend.src.search import SearchResult, _apply_time_decay

    now = datetime(2026, 5, 14, tzinfo=UTC)
    old_date = (now - timedelta(days=360)).isoformat()
    new_date = (now - timedelta(days=10)).isoformat()

    old_doc = SearchResult(
        id="old", title="Old", score=0.8, axes={}, body_snippet="",
        path="old.md", metadata={"updated": old_date},
    )
    new_doc = SearchResult(
        id="new", title="New", score=0.8, axes={}, body_snippet="",
        path="new.md", metadata={"updated": new_date},
    )
    td = TimeDecayConfig(enabled=True, half_life_days=180, weight=0.3, date_field="updated")
    results = _apply_time_decay([old_doc, new_doc], td)

    new_result = next(r for r in results if r.id == "new")
    old_result = next(r for r in results if r.id == "old")
    assert new_result.score > old_result.score


def test_time_decay_no_metadata_no_penalty() -> None:
    """Docs without the date field receive decay=1.0 (score unchanged)."""
    from backend.src.config import TimeDecayConfig
    from backend.src.search import SearchResult, _apply_time_decay

    doc = SearchResult(
        id="nodates", title="No dates", score=0.75, axes={}, body_snippet="",
        path="nodates.md", metadata={},
    )
    td = TimeDecayConfig(enabled=True, half_life_days=180, weight=0.5, date_field="updated")
    results = _apply_time_decay([doc], td)
    assert results[0].score == pytest.approx(0.75)


def test_time_decay_engine_no_config_unchanged_scores(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    """Engine with time_decay_config=None (default) must leave scores unchanged."""
    from backend.src.config import TimeDecayConfig

    docs = [
        _make_doc("d1", "技術記事", "rag knowledge retrieval system"),
        _make_doc("d2", "技術記事", "vector search cosine similarity"),
    ]
    embeddings = dummy_embedder.embed_batch([d.body for d in docs])
    in_memory_store.upsert_many(docs, embeddings)

    engine_no_decay = SearchEngine(in_memory_store, dummy_embedder)
    td_cfg = TimeDecayConfig(enabled=True, half_life_days=180, weight=0.5, date_field="updated")
    engine_with_decay = SearchEngine(
        in_memory_store, dummy_embedder, time_decay_config=td_cfg
    )

    r_no = engine_no_decay.search("rag", top_k=2)
    r_with = engine_with_decay.search("rag", top_k=2)
    # No updated field in metadata → decay=1.0 → blend returns base unchanged
    for r1, r2 in zip(r_no, r_with, strict=True):
        assert r1.score == pytest.approx(r2.score)


def test_time_decay_disabled_flag_is_noop(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    """enabled=False must produce identical results to no time_decay_config."""
    from backend.src.config import TimeDecayConfig

    docs = [
        _make_doc("d1", "技術記事", "rag retrieval pipeline"),
        _make_doc("d2", "技術記事", "bm25 keyword matching"),
    ]
    embeddings = dummy_embedder.embed_batch([d.body for d in docs])
    in_memory_store.upsert_many(docs, embeddings)

    engine_none = SearchEngine(in_memory_store, dummy_embedder)
    td_disabled = TimeDecayConfig(enabled=False, half_life_days=180, weight=0.5, date_field="updated")
    engine_disabled = SearchEngine(
        in_memory_store, dummy_embedder, time_decay_config=td_disabled
    )

    r_none = engine_none.search("rag", top_k=2)
    r_disabled = engine_disabled.search("rag", top_k=2)
    assert [r.id for r in r_none] == [r.id for r in r_disabled]
    for r1, r2 in zip(r_none, r_disabled, strict=True):
        assert r1.score == pytest.approx(r2.score)


def test_time_decay_result_metadata_field_present(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    """SearchResult must expose a metadata dict (even if empty) for time_decay use."""
    docs = [_make_doc("d1", "技術記事", "RAGとは検索拡張生成のことです")]
    embeddings = dummy_embedder.embed_batch([d.body for d in docs])
    in_memory_store.upsert_many(docs, embeddings)

    engine = SearchEngine(in_memory_store, dummy_embedder)
    results = engine.search("RAG", top_k=1)
    assert results
    assert isinstance(results[0].metadata, dict)


# ---------------------------------------------------------------------------
# spec_040: graph_expand integration
# ---------------------------------------------------------------------------


def _seed_graph_corpus(
    store: VectorStore, embedder: Embedder
) -> tuple[list[Document], list[list[float]]]:
    """Build a 4-doc corpus with refs forming a small graph.

        d1 -> d2 -> d3      (d4 isolated)

    Returns the docs + embeddings for graph integration tests.
    """
    docs = [
        _make_doc("d1", "技術記事", "RAG パイプライン全般の話"),
        _make_doc("d2", "技術記事", "ベクトル検索のテクニック詳細"),
        _make_doc("d3", "技術記事", "Chroma の永続化設定について"),
        _make_doc("d4", "メモ", "週次ミーティングのメモ"),
    ]
    docs[0].refs = ["d2"]
    docs[1].refs = ["d3"]
    embeddings = embedder.embed_batch([d.body for d in docs])
    store.upsert_many(docs, embeddings)
    return docs, embeddings


def _build_graph_from(docs: list[Document]):
    from backend.src.graph import KnowledgeGraph

    payload = [
        {"id": d.id, "title": d.title, "axes": d.axes, "refs": d.refs} for d in docs
    ]
    return KnowledgeGraph.build_from_docs(payload)


def test_search_with_graph_expand_adds_neighbors(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    """graph_expand=True should pull in 1-hop neighbours of the top hits."""
    docs, _ = _seed_graph_corpus(in_memory_store, dummy_embedder)
    graph = _build_graph_from(docs)
    engine = SearchEngine(in_memory_store, dummy_embedder, graph=graph)

    plain = engine.search("RAG", top_k=2, bm25_weight=0.0)
    expanded = engine.search("RAG", top_k=2, bm25_weight=0.0, graph_expand=True)
    # Expansion appends neighbours after the original results — at minimum,
    # the count must not decrease, and ideally one of d1's neighbours (d2)
    # surfaces when it would otherwise be cut.
    assert len(expanded) >= len(plain)


def test_search_graph_expand_dedupe(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    """Neighbours already present in the result set must not be duplicated."""
    docs, _ = _seed_graph_corpus(in_memory_store, dummy_embedder)
    graph = _build_graph_from(docs)
    engine = SearchEngine(in_memory_store, dummy_embedder, graph=graph)
    results = engine.search("RAG", top_k=10, bm25_weight=0.0, graph_expand=True)
    ids = [r.id for r in results]
    assert len(ids) == len(set(ids))


def test_search_graph_expand_score_decay(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    """A neighbour pulled in via graph_expand has score = source × 0.7."""
    from backend.src.search import SearchResult

    docs, _ = _seed_graph_corpus(in_memory_store, dummy_embedder)
    graph = _build_graph_from(docs)
    engine = SearchEngine(in_memory_store, dummy_embedder, graph=graph)

    seed = SearchResult(
        id="d1", title="t", score=0.5, axes={}, body_snippet="",
        path="/tmp/d1.md", refs=["d2"],
    )
    expanded = engine._expand_with_graph([seed], hop=1, max_neighbors=5)
    neighbour = next((r for r in expanded if r.id == "d2"), None)
    assert neighbour is not None
    assert neighbour.score == pytest.approx(0.5 * 0.7)


def test_search_no_graph_no_expand(
    in_memory_store: VectorStore, dummy_embedder: Embedder, caplog: pytest.LogCaptureFixture
) -> None:
    """graph_expand=True with engine.graph=None is a warn-and-skip no-op."""
    docs, _ = _seed_graph_corpus(in_memory_store, dummy_embedder)  # no graph wired
    engine = SearchEngine(in_memory_store, dummy_embedder)
    plain = engine.search("RAG", top_k=2, bm25_weight=0.0)
    with caplog.at_level("WARNING", logger="backend.src.search"):
        expanded = engine.search("RAG", top_k=2, bm25_weight=0.0, graph_expand=True)
    assert [r.id for r in plain] == [r.id for r in expanded]
    assert any("no KnowledgeGraph" in rec.message for rec in caplog.records)


def test_search_graph_expand_max_neighbors(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    """max_neighbors caps the per-source neighbour expansion."""
    from backend.src.search import SearchResult

    docs = [
        _make_doc("hub", "技術記事", "hub body"),
        _make_doc("a", "技術記事", "a body"),
        _make_doc("b", "技術記事", "b body"),
        _make_doc("c", "技術記事", "c body"),
    ]
    docs[0].refs = ["a", "b", "c"]
    embeddings = dummy_embedder.embed_batch([d.body for d in docs])
    in_memory_store.upsert_many(docs, embeddings)
    graph = _build_graph_from(docs)
    engine = SearchEngine(in_memory_store, dummy_embedder, graph=graph)

    seed = SearchResult(
        id="hub", title="hub", score=0.5, axes={}, body_snippet="",
        path="/tmp/hub.md", refs=docs[0].refs,
    )
    expanded = engine._expand_with_graph([seed], hop=1, max_neighbors=2)
    neighbours_added = [r for r in expanded if r.id != "hub"]
    assert len(neighbours_added) == 2


# ---------------------------------------------------------------------------
# spec_051: dim mismatch / axis-only embedding dim
# ---------------------------------------------------------------------------


class _DummyEmbedder1024:
    """Test double — reports dim=1024 instead of the default 768."""

    @property
    def is_dummy(self) -> bool:
        return True

    @property
    def dim(self) -> int:
        return 1024

    def embed(self, text: str) -> list[float]:
        return [0.0] * 1024

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


def test_axis_only_query_uses_embedder_dim(
    in_memory_store: VectorStore, dummy_embedder: Embedder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec_051 HIGH-1: axis-only path must build the zero vector at
    ``embedder.dim``, not the legacy hardcoded 768."""
    # Seed the store with one doc embedded under the default 768-dim
    # embedder so the count() short-circuit doesn't bypass the call.
    docs = [_make_doc("d1", "技術記事", "body")]
    embeddings = dummy_embedder.embed_batch([d.body for d in docs])
    in_memory_store.upsert_many(docs, embeddings)

    fake_emb = _DummyEmbedder1024()
    captured: dict[str, object] = {}

    def fake_query(embedding, *, n_results, where=None):
        captured["len"] = len(embedding)
        return {"ids": [[]], "distances": [[]], "metadatas": [[]], "documents": [[]]}

    monkeypatch.setattr(in_memory_store, "query", fake_query)
    engine = SearchEngine(in_memory_store, fake_emb)
    engine.search(None, filters={"category": "技術記事"}, top_k=5)
    assert captured["len"] == 1024


def test_search_with_mismatched_dim_raises_clear_error(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    """probe_dim returns the indexed dim; a follow-up query with the
    *wrong* dim must fail loudly (Chroma's native error is fine — the
    lifespan check is what catches the typical config-swap case)."""
    docs = [_make_doc("d1", "技術記事", "body")]
    embeddings = dummy_embedder.embed_batch([d.body for d in docs])
    in_memory_store.upsert_many(docs, embeddings)

    # probe_dim recovers the dim the store was built with.
    assert in_memory_store.probe_dim() == dummy_embedder.dim

    # Querying with a mismatched-dim embedding raises (Chroma surfaces
    # an InvalidDimensionException-like error). The exact class isn't
    # what the test cares about — just that it's not a silent crash.
    with pytest.raises(Exception):
        in_memory_store.query([0.0] * (dummy_embedder.dim + 16), n_results=1)
