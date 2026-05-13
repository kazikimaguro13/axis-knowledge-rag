"""Integration tests for SearchEngine. Run via: python -m backend.tests.test_search"""

import sys
from pathlib import Path

from backend.src.embedder import Embedder
from backend.src.loader import Document
from backend.src.normalizer import Normalizer
from backend.src.search import SearchEngine, SearchResult, _build_where
from backend.src.vector_store import VectorStore


def _make_doc(
    doc_id: str, category: str, body: str = "body text",
    normalizer: Normalizer | None = None,
) -> Document:
    doc = Document(
        id=doc_id,
        title=f"Title {doc_id}",
        axes={"category": category, "level": "中級"},
        tags=[],
        refs=[],
        body=body,
        path=Path(f"/tmp/{doc_id}.md"),
        raw_meta={},
    )
    if normalizer is not None:
        doc.normalized_title = normalizer(doc.title)
        doc.normalized_body = normalizer(doc.body)
        doc.normalized_axes = {k: normalizer(str(v)) for k, v in doc.axes.items()}
        doc.normalized_tags = [normalizer(t) for t in doc.tags]
    return doc


def _setup() -> tuple[VectorStore, Embedder, SearchEngine]:
    normalizer = Normalizer()
    store = VectorStore(in_memory=True)
    store.reset()  # Chroma EphemeralClient はプロセス内で状態を共有するため毎回 reset
    embedder = Embedder(force_dummy=True)
    docs = [
        _make_doc("d1", "技術記事", "RAGとはRetrieval-Augmented Generationの略です", normalizer),
        _make_doc("d2", "技術記事", "ベクトル検索はコサイン類似度を用います", normalizer),
        _make_doc("d3", "メモ", "今日の会議メモ: プロジェクト進捗確認", normalizer),
    ]
    embeddings = embedder.embed_batch([d.normalized_body for d in docs])
    store.upsert_many(docs, embeddings)
    return store, embedder, SearchEngine(store, embedder, normalizer)


def test_query_no_filter_returns_all() -> None:
    """フィルタなし query — 3件全部返る"""
    _, _, engine = _setup()
    results = engine.search("RAGとは", top_k=10)
    assert len(results) == 3, f"expected 3, got {len(results)}"


def test_query_with_category_filter() -> None:
    """category=技術記事 フィルタ — 技術記事の2件だけ返る"""
    _, _, engine = _setup()
    results = engine.search("RAGとは", filters={"category": "技術記事"}, top_k=10)
    assert len(results) == 2, f"expected 2, got {len(results)}"
    for r in results:
        assert r.axes.get("category") == "技術記事", f"unexpected category: {r.axes}"


def test_axis_only_no_query_with_filter() -> None:
    """query=None + axis-only — フィルタ一致のみ返る"""
    _, _, engine = _setup()
    results = engine.search(None, filters={"category": "メモ"}, top_k=10)
    assert len(results) == 1, f"expected 1, got {len(results)}"
    assert results[0].id == "d3"


def test_score_in_range() -> None:
    """score が 0〜1 の範囲に収まる"""
    _, _, engine = _setup()
    results = engine.search("RAGとは", top_k=10)
    for r in results:
        assert 0.0 <= r.score <= 1.0, f"score out of range: {r.score} for {r.id}"


def test_result_has_required_fields() -> None:
    """SearchResult が Day4 (rag.py) に必要なフィールドを持つ"""
    _, _, engine = _setup()
    results = engine.search("RAGとは", top_k=1)
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


def test_build_where_single_key() -> None:
    """単一フィルタは $and なしの flat dict を返す"""
    w = _build_where({"category": "技術記事"})
    assert w == {"axis_category": "技術記事"}


def test_build_where_multi_key() -> None:
    """複数フィルタは $and 形式を返す"""
    w = _build_where({"category": "技術記事", "level": "中級"})
    assert w is not None
    assert "$and" in w
    items = w["$and"]
    assert {"axis_category": "技術記事"} in items
    assert {"axis_level": "中級"} in items


def test_build_where_empty_returns_none() -> None:
    assert _build_where({}) is None


if __name__ == "__main__":
    tests = [
        test_query_no_filter_returns_all,
        test_query_with_category_filter,
        test_axis_only_no_query_with_filter,
        test_score_in_range,
        test_result_has_required_fields,
        test_build_where_single_key,
        test_build_where_multi_key,
        test_build_where_empty_returns_none,
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
