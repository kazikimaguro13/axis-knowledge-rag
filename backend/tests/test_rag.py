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
