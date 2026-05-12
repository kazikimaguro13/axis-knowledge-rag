"""Integration tests for RAGPipeline (DUMMY mode only). Run via: python -m backend.tests.test_rag"""

import sys
from pathlib import Path

from backend.src.embedder import Embedder
from backend.src.loader import Document
from backend.src.rag import RAGPipeline, Answer
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


def _setup() -> tuple[VectorStore, Embedder, SearchEngine, RAGPipeline]:
    store = VectorStore(in_memory=True)
    embedder = Embedder(force_dummy=True)
    docs = [
        _make_doc("doc_001", "技術記事", "RAGとはRetrieval-Augmented Generationの略です"),
        _make_doc("doc_002", "技術記事", "ベクトル検索はコサイン類似度を用います"),
        _make_doc("doc_003", "メモ", "今日の会議メモ: プロジェクト進捗確認"),
    ]
    embeddings = embedder.embed_batch([d.body for d in docs])
    store.upsert_many(docs, embeddings)
    engine = SearchEngine(store, embedder)
    rag = RAGPipeline(engine, force_dummy=True)
    return store, embedder, engine, rag


def test_answer_is_dummy() -> None:
    """force_dummy=True の場合 is_dummy=True で返る"""
    _, _, _, rag = _setup()
    ans = rag.answer("dummy question")
    assert ans.is_dummy is True, f"expected is_dummy=True, got {ans.is_dummy}"
    assert isinstance(ans, Answer)


def test_answer_sources_has_top_k_items() -> None:
    """sources に top_k 件入る"""
    _, _, _, rag = _setup()
    ans = rag.answer("dummy question", top_k=2)
    assert len(ans.sources) == 2, f"expected 2 sources, got {len(ans.sources)}"


def test_answer_sources_all_when_top_k_exceeds_collection() -> None:
    """top_k がコレクション件数を超えても全件返る"""
    _, _, _, rag = _setup()
    ans = rag.answer("dummy question", top_k=10)
    assert len(ans.sources) == 3, f"expected 3 sources, got {len(ans.sources)}"


def test_answer_no_results_cited_ids_empty() -> None:
    """結果 0 件の場合 cited_ids は空 list"""
    store = VectorStore(in_memory=True)
    embedder = Embedder(force_dummy=True)
    engine = SearchEngine(store, embedder)
    rag = RAGPipeline(engine, force_dummy=True)
    ans = rag.answer("empty question", filters={"category": "存在しないカテゴリ"})
    assert ans.cited_ids == [], f"expected empty cited_ids, got {ans.cited_ids}"
    assert ans.sources == []


def test_answer_text_is_string() -> None:
    """text が str"""
    _, _, _, rag = _setup()
    ans = rag.answer("dummy question")
    assert isinstance(ans.text, str)
    assert len(ans.text) > 0


def test_answer_cited_ids_subset_of_sources() -> None:
    """cited_ids は sources の id のサブセット"""
    _, _, _, rag = _setup()
    ans = rag.answer("dummy question", top_k=3)
    source_ids = {s.id for s in ans.sources}
    for cid in ans.cited_ids:
        assert cid in source_ids, f"cited_id {cid!r} not in sources"


def test_pipeline_is_dummy_property() -> None:
    """is_dummy プロパティが force_dummy と一致"""
    store = VectorStore(in_memory=True)
    embedder = Embedder(force_dummy=True)
    engine = SearchEngine(store, embedder)
    rag = RAGPipeline(engine, force_dummy=True)
    assert rag.is_dummy is True


def test_answer_with_category_filter() -> None:
    """category フィルタを渡すと sources が絞られる"""
    _, _, _, rag = _setup()
    ans = rag.answer("dummy question", filters={"category": "技術記事"}, top_k=10)
    for s in ans.sources:
        assert s.axes.get("category") == "技術記事", f"unexpected axes: {s.axes}"


if __name__ == "__main__":
    tests = [
        test_answer_is_dummy,
        test_answer_sources_has_top_k_items,
        test_answer_sources_all_when_top_k_exceeds_collection,
        test_answer_no_results_cited_ids_empty,
        test_answer_text_is_string,
        test_answer_cited_ids_subset_of_sources,
        test_pipeline_is_dummy_property,
        test_answer_with_category_filter,
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
