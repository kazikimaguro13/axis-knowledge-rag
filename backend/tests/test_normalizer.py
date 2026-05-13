"""Tests for normalizer.normalize_text."""

import pytest

from backend.src.normalizer import (
    Normalizer,
    NormalizerOptions,
    normalize_text,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ＲＡＧ", "rag"),
        ("ＡＢＣ", "abc"),
        ("２０２６", "2026"),
        ("ラグ", "らぐ"),
        ("プロンプト", "ぷろんぷと"),
        ("RAGとベクトル検索", "ragとべくとる検索"),
        ("バカ", "ばか"),
        ("ピ", "ぴ"),
        ("RAG", "rag"),
        ("Claude API", "claude api"),
        ("漢字", "漢字"),
        ("検索", "検索"),
        ("", ""),
        ("Hello World", "hello world"),
        ("Hello　World", "hello world"),
    ],
)
def test_normalize_text(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_idempotent() -> None:
    s = "ＲＡＧとカタカナ"
    assert normalize_text(normalize_text(s)) == normalize_text(s)


@pytest.mark.parametrize(
    "a,b",
    [
        ("RAG", "ＲＡＧ"),
        ("ラグ", "らぐ"),
        ("Claude API", "ｃｌａｕｄｅ ＡＰＩ"),
        ("プロンプトエンジニアリング", "ぷろんぷとえんじにありんぐ"),
    ],
)
def test_query_matches_index(a: str, b: str) -> None:
    assert normalize_text(a) == normalize_text(b)


def test_options_disable_katakana() -> None:
    opts = NormalizerOptions(katakana_to_hiragana=False)
    assert normalize_text("ラグ", opts) == "ラグ"


def test_options_disable_nfkc() -> None:
    opts = NormalizerOptions(nfkc=False, lowercase=False)
    assert normalize_text("ＲＡＧ", opts) == "ＲＡＧ"


def test_options_disable_lowercase() -> None:
    opts = NormalizerOptions(lowercase=False)
    assert normalize_text("RAG", opts) == "RAG"


def test_normalizer_class() -> None:
    n = Normalizer()
    assert n("ＲＡＧ") == "rag"


def test_normalizer_from_config() -> None:
    n2 = Normalizer.from_config({"normalization": {"katakana_to_hiragana": False}})
    assert n2("ラグ") == "ラグ"
