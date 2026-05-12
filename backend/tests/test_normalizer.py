"""Tests for normalizer.normalize_text. Run via: python -m backend.tests.test_normalizer"""

import sys

from backend.src.normalizer import (
    Normalizer,
    NormalizerOptions,
    normalize_text,
)


def _assert_eq(actual: str, expected: str, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_nfkc_fullwidth_alpha() -> None:
    _assert_eq(normalize_text("ＲＡＧ"), "rag", "fullwidth alpha")
    _assert_eq(normalize_text("ＡＢＣ"), "abc", "fullwidth ABC")


def test_nfkc_fullwidth_digit() -> None:
    _assert_eq(normalize_text("２０２６"), "2026", "fullwidth digit")


def test_katakana_to_hiragana() -> None:
    _assert_eq(normalize_text("ラグ"), "らぐ", "kata->hira")
    _assert_eq(normalize_text("プロンプト"), "ぷろんぷと", "kata->hira longer")


def test_mixed_text() -> None:
    # 漢字はそのまま維持、カタカナのみひらがなに変換
    _assert_eq(normalize_text("RAGとベクトル検索"), "ragとべくとる検索", "mixed")


def test_kana_with_dakuten() -> None:
    # 濁点付き
    _assert_eq(normalize_text("バカ"), "ばか", "dakuten")
    _assert_eq(normalize_text("ピ"), "ぴ", "handakuten")


def test_lowercase() -> None:
    _assert_eq(normalize_text("RAG"), "rag", "lowercase ascii")
    _assert_eq(normalize_text("Claude API"), "claude api", "lowercase mixed")


def test_kanji_unchanged() -> None:
    _assert_eq(normalize_text("漢字"), "漢字", "kanji unchanged")
    _assert_eq(normalize_text("検索"), "検索", "kanji unchanged 2")


def test_idempotent() -> None:
    s = "ＲＡＧとカタカナ"
    _assert_eq(normalize_text(normalize_text(s)), normalize_text(s), "idempotent")


def test_query_matches_index() -> None:
    # 表記ゆれ吸収の核心: 違う書き方が同じになる
    assert normalize_text("RAG") == normalize_text("ＲＡＧ")
    assert normalize_text("ラグ") == normalize_text("らぐ")
    assert normalize_text("Claude API") == normalize_text("ｃｌａｕｄｅ ＡＰＩ")
    assert normalize_text("プロンプトエンジニアリング") == normalize_text("ぷろんぷとえんじにありんぐ")


def test_options_disable_katakana() -> None:
    opts = NormalizerOptions(katakana_to_hiragana=False)
    _assert_eq(normalize_text("ラグ", opts), "ラグ", "katakana preserved")


def test_options_disable_nfkc() -> None:
    opts = NormalizerOptions(nfkc=False, lowercase=False)
    _assert_eq(normalize_text("ＲＡＧ", opts), "ＲＡＧ", "nfkc skipped")


def test_options_disable_lowercase() -> None:
    opts = NormalizerOptions(lowercase=False)
    _assert_eq(normalize_text("RAG", opts), "RAG", "lowercase skipped")


def test_normalizer_class() -> None:
    n = Normalizer()
    _assert_eq(n("ＲＡＧ"), "rag", "class default")
    n2 = Normalizer.from_config({"normalization": {"katakana_to_hiragana": False}})
    _assert_eq(n2("ラグ"), "ラグ", "from_config disables kana")


def test_empty_string() -> None:
    _assert_eq(normalize_text(""), "", "empty")


def test_whitespace_preserved() -> None:
    _assert_eq(normalize_text("Hello World"), "hello world", "ws preserved")


def test_zenkaku_space() -> None:
    # NFKC で全角スペースは半角スペースに
    _assert_eq(normalize_text("Hello　World"), "hello world", "zenkaku space")


if __name__ == "__main__":
    tests = [
        test_nfkc_fullwidth_alpha,
        test_nfkc_fullwidth_digit,
        test_katakana_to_hiragana,
        test_mixed_text,
        test_kana_with_dakuten,
        test_lowercase,
        test_kanji_unchanged,
        test_idempotent,
        test_query_matches_index,
        test_options_disable_katakana,
        test_options_disable_nfkc,
        test_options_disable_lowercase,
        test_normalizer_class,
        test_empty_string,
        test_whitespace_preserved,
        test_zenkaku_space,
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
    print(f"\n{len(tests) - failed}/{len(tests)} PASSED")
    sys.exit(1 if failed else 0)
