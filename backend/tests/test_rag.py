"""Integration tests for RAGPipeline (DUMMY mode only)."""

from pathlib import Path

import pytest

from backend.src.embedder import Embedder
from backend.src.loader import Document
from backend.src.rag import Answer, RAGPipeline
from backend.src.search import SearchEngine
from backend.src.vector_store import VectorStore


def _make_doc(doc_id: str, category: str, body: str = "body text") -> Document:
    return Document(
        id=doc_id,
        title=f"Title {doc_id}",
        axes={"category": category, "level": "中級"},
        tags=[],
        refs=[],
        body=body,
        path=Path(f"/tmp/{doc_id}.md"),
        raw_meta={},
    )


@pytest.fixture
def rag_pipeline(in_memory_store: VectorStore, dummy_embedder: Embedder) -> RAGPipeline:
    docs = [
        _make_doc("doc_001", "技術記事", "RAGとはRetrieval-Augmented Generationの略です"),
        _make_doc("doc_002", "技術記事", "ベクトル検索はコサイン類似度を用います"),
        _make_doc("doc_003", "メモ", "今日の会議メモ: プロジェクト進捗確認"),
    ]
    embeddings = dummy_embedder.embed_batch([d.body for d in docs])
    in_memory_store.upsert_many(docs, embeddings)
    engine = SearchEngine(in_memory_store, dummy_embedder)
    return RAGPipeline(engine, force_dummy=True)


def test_answer_is_dummy(rag_pipeline: RAGPipeline) -> None:
    ans = rag_pipeline.answer("dummy question")
    assert ans.is_dummy is True
    assert isinstance(ans, Answer)


def test_answer_sources_has_top_k_items(rag_pipeline: RAGPipeline) -> None:
    ans = rag_pipeline.answer("dummy question", top_k=2)
    assert len(ans.sources) == 2


def test_answer_sources_all_when_top_k_exceeds_collection(rag_pipeline: RAGPipeline) -> None:
    ans = rag_pipeline.answer("dummy question", top_k=10)
    assert len(ans.sources) == 3


def test_answer_no_results_cited_ids_empty(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    engine = SearchEngine(in_memory_store, dummy_embedder)
    rag = RAGPipeline(engine, force_dummy=True)
    ans = rag.answer("empty question", filters={"category": "存在しないカテゴリ"})
    assert ans.cited_ids == []
    assert ans.sources == []


def test_answer_text_is_string(rag_pipeline: RAGPipeline) -> None:
    ans = rag_pipeline.answer("dummy question")
    assert isinstance(ans.text, str)
    assert len(ans.text) > 0


def test_answer_cited_ids_subset_of_sources(rag_pipeline: RAGPipeline) -> None:
    ans = rag_pipeline.answer("dummy question", top_k=3)
    source_ids = {s.id for s in ans.sources}
    for cid in ans.cited_ids:
        assert cid in source_ids


def test_pipeline_is_dummy_property(
    in_memory_store: VectorStore, dummy_embedder: Embedder
) -> None:
    engine = SearchEngine(in_memory_store, dummy_embedder)
    rag = RAGPipeline(engine, force_dummy=True)
    assert rag.is_dummy is True


def test_answer_with_category_filter(rag_pipeline: RAGPipeline) -> None:
    ans = rag_pipeline.answer("dummy question", filters={"category": "技術記事"}, top_k=10)
    for s in ans.sources:
        assert s.axes.get("category") == "技術記事"


# ---------------------------------------------------------------------------
# spec_031: build_context (parent-doc aware)
# ---------------------------------------------------------------------------


def test_build_context_uses_body_full_when_present() -> None:
    from backend.src.rag import build_context
    from backend.src.search import SearchResult

    full = "Full parent text body that should appear in context."
    r = SearchResult(
        id="doc_001#alpha",
        title="Alpha",
        score=0.9,
        axes={"category": "技術記事"},
        body_snippet=full[:30],
        path="doc_001",
        refs=[],
        body_full=full,
    )
    out = build_context([r], max_chars=8000)
    assert full in out
    assert "## 出典 1: [doc_001#alpha] Alpha" in out
    assert "(file: doc_001)" in out


def test_build_context_falls_back_to_snippet_when_no_body_full() -> None:
    from backend.src.rag import build_context
    from backend.src.search import SearchResult

    r = SearchResult(
        id="doc_001",
        title="Legacy Doc",
        score=0.9,
        axes={},
        body_snippet="Just a snippet.",
        path="/tmp/doc_001.md",
        refs=[],
    )
    out = build_context([r])
    assert "Just a snippet." in out


# ---------------------------------------------------------------------------
# spec_032: rag.chat() (conversational, dummy mode)
# ---------------------------------------------------------------------------


def test_chat_creates_session_and_persists_turn(rag_pipeline: RAGPipeline) -> None:
    from backend.src.conversation import ConversationStore

    store = ConversationStore()
    resp = rag_pipeline.chat("dummy question", store=store)
    assert resp.session_id
    assert resp.is_dummy is True
    # user + assistant persisted
    hist = store.get_history(resp.session_id, last_n_turns=6)
    assert len(hist) == 2
    assert hist[0].role == "user"
    assert hist[1].role == "assistant"


def test_chat_reuses_session(rag_pipeline: RAGPipeline) -> None:
    from backend.src.conversation import ConversationStore

    store = ConversationStore()
    r1 = rag_pipeline.chat("first", store=store)
    r2 = rag_pipeline.chat("second", session_id=r1.session_id, store=store)
    assert r2.session_id == r1.session_id
    # 2 turns = 4 messages
    assert len(store.get_history(r1.session_id, last_n_turns=6)) == 4


def test_chat_no_rewrite_when_history_empty(rag_pipeline: RAGPipeline) -> None:
    from backend.src.conversation import ConversationStore

    store = ConversationStore()
    resp = rag_pipeline.chat("first turn", store=store)
    # No prior turns → rewriter returns original → rewritten_question=None
    assert resp.rewritten_question is None


# ---------------------------------------------------------------------------
# spec_034: [N] citation marker end-to-end
# ---------------------------------------------------------------------------


class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeBlock(text)]


class _FakeMessages:
    def __init__(self, text: str) -> None:
        self._text = text

    def create(self, **_kw):  # noqa: ANN003
        return _FakeResponse(self._text)


class _FakeAnthropic:
    def __init__(self, text: str) -> None:
        self.messages = _FakeMessages(text)


def _make_real_pipeline(
    rag_pipeline: RAGPipeline, claude_reply: str
) -> RAGPipeline:
    """Flip a dummy pipeline into 'real' mode with a stubbed Claude client."""
    rag_pipeline._use_dummy = False  # noqa: SLF001
    rag_pipeline._client = _FakeAnthropic(claude_reply)  # noqa: SLF001
    return rag_pipeline


def test_answer_maps_n_markers_to_source_ids(rag_pipeline: RAGPipeline) -> None:
    rag = _make_real_pipeline(
        rag_pipeline, "First fact[1]. Second fact[2]."
    )
    ans = rag.answer("dummy question", top_k=2)
    # [1] -> sources[0].id, [2] -> sources[1].id
    assert ans.cited_ids == [ans.sources[0].id, ans.sources[1].id]
    assert "[1]" in ans.text and "[2]" in ans.text
    assert ans.is_dummy is False


def test_answer_strips_out_of_range_n_marker(rag_pipeline: RAGPipeline) -> None:
    rag = _make_real_pipeline(
        rag_pipeline, "Real claim[1]. Fake claim[9]."
    )
    ans = rag.answer("dummy question", top_k=2)
    assert "[9]" not in ans.text
    assert "[1]" in ans.text
    assert ans.cited_ids == [ans.sources[0].id]


def test_answer_canonicalises_csv_marker(rag_pipeline: RAGPipeline) -> None:
    rag = _make_real_pipeline(rag_pipeline, "Both back this[1, 2].")
    ans = rag.answer("dummy question", top_k=2)
    assert "[1][2]" in ans.text
    assert set(ans.cited_ids) == {ans.sources[0].id, ans.sources[1].id}


def test_build_context_respects_max_chars_budget() -> None:
    from backend.src.rag import build_context
    from backend.src.search import SearchResult

    big_text = "x" * 5000
    results = [
        SearchResult(
            id=f"d#{i}",
            title=f"T{i}",
            score=1.0,
            axes={},
            body_snippet="s",
            path=f"d{i}",
            refs=[],
            body_full=big_text,
        )
        for i in range(5)
    ]
    out = build_context(results, max_chars=6000)
    # Should fit at most one full block (~5000+header), the next should be dropped.
    assert out.count("## 出典") == 1
