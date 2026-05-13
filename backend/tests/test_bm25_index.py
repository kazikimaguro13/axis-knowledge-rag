"""Unit tests for BM25Index (spec_029)."""

import pytest

from backend.src.bm25_index import BM25Index, _tokenize
from backend.src.normalizer import Normalizer


def test_tokenize_character_ngrams() -> None:
    """`_tokenize` emits unigrams + bigrams over normalized text."""
    out = _tokenize("あいう")
    assert "あ" in out
    assert "い" in out
    assert "う" in out
    assert "あい" in out
    assert "いう" in out
    assert len(out) == 5  # 3 unigrams + 2 bigrams


def test_tokenize_empty_returns_empty_list() -> None:
    assert _tokenize("") == []


def test_bm25_index_basic_scoring() -> None:
    """Documents that match the query term must outrank unrelated ones."""
    normalizer = Normalizer.identity()
    idx = BM25Index.build(
        [
            ("doc_001", "chromadb の永続化設計について"),
            ("doc_002", "fastapi で軸検索 api を作る"),
            ("doc_003", "rag パイプラインの設計判断"),
        ],
        normalizer,
    )
    scores = idx.score("chromadb")
    assert scores["doc_001"] > scores["doc_002"]
    assert scores["doc_001"] > scores["doc_003"]


def test_bm25_index_empty_query_returns_empty_dict() -> None:
    idx = BM25Index.build([("doc_001", "本文")], Normalizer.identity())
    assert idx.score("") == {}


def test_bm25_index_no_matches_returns_normalized_scores() -> None:
    """Even when nothing matches, scores stay in `[0, 1]` after min-max norm."""
    idx = BM25Index.build([("doc_001", "本文")], Normalizer.identity())
    scores = idx.score("まったく関係ないクエリ")
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_bm25_index_len_matches_corpus() -> None:
    idx = BM25Index.build(
        [("a", "x"), ("b", "y"), ("c", "z")], Normalizer.identity()
    )
    assert len(idx) == 3


def test_bm25_index_uses_normalizer_for_query() -> None:
    """The query is run through the index's Normalizer before tokenization."""
    # Default normalizer lowercases — "ChromaDB" -> "chromadb"
    # 3+ docs needed so BM25 IDF gives non-zero weights.
    idx = BM25Index.build(
        [
            ("doc_001", "chromadb の話"),
            ("doc_002", "全然関係ない本文"),
            ("doc_003", "別の話題のメモ"),
        ],
        Normalizer(),  # lowercase + nfkc + kata→hira
    )
    scores = idx.score("ChromaDB")  # mixed case
    assert scores["doc_001"] > scores["doc_002"]


def test_bm25_index_single_doc_corpus() -> None:
    """Single-doc corpus must not blow up min-max normalization."""
    idx = BM25Index.build([("doc_001", "唯一の本文")], Normalizer.identity())
    scores = idx.score("唯一")
    # With one doc, min == max, so normalized score is 0.0 (degenerate case)
    assert scores["doc_001"] == pytest.approx(0.0)
