# spec_008: Day 8 — normalizer.py (NFKC + カタカナ→ひらがな + 全角/半角)

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001〜007 (v0.1.0 リリース済み前提), `docs/spec-v2.md` Day 8 行

## 1. 目的

```
[現状]
- v0.1.0 リリース済み。loader / embedder / search / rag / Streamlit / Docker が動く
- 検索は素のテキスト類似度 + 軸 exact match のみ
- "RAG" と "ＲＡＧ"、"らぐ" と "ラグ" が別物として扱われる
- 日本語ナレッジ特化を謳っているのに、表記ゆれに弱い

[変更後]
- `backend/src/normalizer.py` が以下を提供:
  - `normalize_text(text: str) -> str` — NFKC + カタカナ→ひらがな + lowercase
  - `Normalizer` クラス — `config.yml` の `normalization` セクションに基づいて on/off 切替
- `tests/test_normalizer.py` で 20+ パターンを assert
- Day 9 (統合) のために API を確定
```

差別化キモの 1 つ目。**3 週間プランで最低 1 個入れる差別化機能** (仕様書 11 章) のうち、これが最優先。

## 2. 制約

### 触ってよいファイル

- `backend/src/normalizer.py` — 新規
- `backend/tests/test_normalizer.py` — 新規 (まだ pytest 化前なので assert ベース)
- `config.yml` — `normalization` セクションが既にある (spec_001 時点で配置済み)、必要なら微調整
- `docs/normalizer.md` — 新規 (簡潔な仕組み解説、Day 13 で全 docs まとめる前段)
- `CHANGELOG.md`

### 触ってはいけないもの

- `backend/src/{loader,embedder,vector_store,search,rag}.py` — 統合は Day 9 (spec_009)。本日は normalizer 単体実装のみ
- `_ai_workspace/`、`docs/spec-v2.md`
- `streamlit_app.py`

### コーディングルール

- Python 標準ライブラリのみで実装 (`unicodedata` + 自前のカナ変換)。**追加依存ゼロ**
- カナ変換は code point shift (`カ` (0x30AB) → `か` (0x304B) は +0xE0 ではなく -0x60 で計算する側)
- `Normalizer` は `config.yml` の `normalization.{nfkc, katakana_to_hiragana, lowercase}` フラグを尊重
- pure function `normalize_text` も export し、設定不要のクイック呼び出しを許可

## 3. やってほしいこと

### 3-1. `backend/src/normalizer.py`

```python
"""Japanese-aware text normalization.

NFKC + カタカナ→ひらがな + lowercase を組み合わせ、検索クエリと
インデックス対象テキストを揃える。LangChain / 外部ライブラリ非依存。
"""

import logging
import unicodedata
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# カタカナブロック (U+30A1〜U+30F6) → ひらがな (U+3041〜U+3096) のシフト量
_KATAKANA_START = 0x30A1
_KATAKANA_END = 0x30F6
_HIRAGANA_START = 0x3041


def _katakana_to_hiragana(text: str) -> str:
    out: list[str] = []
    for ch in text:
        cp = ord(ch)
        if _KATAKANA_START <= cp <= _KATAKANA_END:
            out.append(chr(cp - _KATAKANA_START + _HIRAGANA_START))
        else:
            out.append(ch)
    return "".join(out)


@dataclass(frozen=True)
class NormalizerOptions:
    nfkc: bool = True
    katakana_to_hiragana: bool = True
    lowercase: bool = True


def normalize_text(text: str, options: NormalizerOptions | None = None) -> str:
    opts = options or NormalizerOptions()
    s = text
    if opts.nfkc:
        s = unicodedata.normalize("NFKC", s)
    if opts.katakana_to_hiragana:
        s = _katakana_to_hiragana(s)
    if opts.lowercase:
        s = s.lower()
    return s


class Normalizer:
    """Stateful normalizer driven by config.yml `normalization` section."""

    def __init__(self, options: NormalizerOptions | None = None) -> None:
        self._opts = options or NormalizerOptions()

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "Normalizer":
        n = config.get("normalization", {}) or {}
        return cls(
            NormalizerOptions(
                nfkc=bool(n.get("nfkc", True)),
                katakana_to_hiragana=bool(n.get("katakana_to_hiragana", True)),
                lowercase=bool(n.get("lowercase", True)),
            )
        )

    def __call__(self, text: str) -> str:
        return normalize_text(text, self._opts)

    @property
    def options(self) -> NormalizerOptions:
        return self._opts
```

### 3-2. `backend/tests/test_normalizer.py`

20+ パターンの assert。最低限カバーするケース:

```python
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
    _assert_eq(normalize_text("RAGとベクトル検索"), "ragとべくとるけんさく", "mixed")


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
```

### 3-3. `docs/normalizer.md`

200〜400 行の解説。仕様書 Day 13 で全 docs を整える前段。

```markdown
# Text Normalization

axis-knowledge-rag は日本語ナレッジに特化した検索を行うため、検索クエリと
インデックス対象テキストの両方に NFKC + カタカナ→ひらがな + lowercase の
正規化パイプラインを適用します。

## なぜ必要か

日本語テキストは同じ意味を複数の書き方で表現できる:

| 書き方 | 例 |
|---|---|
| 半角 / 全角 ASCII | `RAG` vs `ＲＡＧ` |
| カタカナ / ひらがな | `ラグ` vs `らぐ` |
| 全角スペース | `Hello World` vs `Hello　World` |
| 大文字 / 小文字 | `Claude` vs `claude` |

検索エンジンが「これらは同じ」と判定できないと、ユーザーは「何度も書き方を
変えて検索する」という非生産的なループに陥ります。

## 適用順序

1. **NFKC 正規化** (`unicodedata.normalize`) — 全角 ASCII → 半角、全角スペース → 半角スペース、半角カナ → 全角カナ
2. **カタカナ→ひらがな** — U+30A1〜U+30F6 を U+3041〜U+3096 にシフト
3. **小文字化** — `str.lower()`

各ステップは `config.yml` でオン/オフできます (例: 中国語版を扱うなら katakana_to_hiragana=false にする)。

## 適用範囲 (Day 9 で統合予定)

- 検索クエリ (ユーザー入力) → 必ず normalize
- インデックス対象 (Document body) → 埋め込み生成前に normalize した別フィールドを Chroma metadata に格納し、軸/タグ exact match の前段で利用
- 軸の値 / タグ → normalize して保存・検索する

## 制限

- 漢字の異体字 (例: `斎`/`齋`) は対応しない
- 送り仮名の揺れ (`引き渡す`/`引渡す`) は対応しない (Week 3 / v0.4 候補)
- 英語の語尾変化 (`run`/`running`) は対応しない (ステミング非対応)

これらは normalizer の責務外。検索結果のリコール向上は別レイヤーで取り組む。
```

### 3-4. 動作確認

```bash
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag"
python -m backend.tests.test_normalizer

# 期待: 16/16 PASSED
```

### 3-5. コミット

1. `feat: implement Japanese text normalizer (NFKC + kana + lowercase)`
2. `test: add 16 normalizer cases (assert-based)`
3. `docs: add docs/normalizer.md explaining the pipeline`
4. `docs: changelog Day 8`

`git push origin main` (dev-b)

### 3-6. result_008.md

特に書くこと:

- 16 テストの全 PASS ログ
- カタカナ→ひらがな変換の境界 (`ヴ`(U+30F4) などのエッジケース) を検証したか
- normalize の前後で文字数が変わるケース (NFKC で半角カナ→全角カナで 1 文字増える等) があれば記載

## 4. 成功条件

- [ ] `normalize_text("RAG") == normalize_text("ＲＡＧ") == "rag"`
- [ ] `normalize_text("ラグ") == normalize_text("らぐ") == "らぐ"`
- [ ] `Normalizer.from_config({"normalization": {"katakana_to_hiragana": False}})("ラグ") == "ラグ"`
- [ ] 全 16 テスト PASS
- [ ] 標準ライブラリのみ (`unicodedata` 以外の外部 import なし)
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_008.md`

## 6. 質問

- **`ヴ` (U+30F4) の扱い**: ひらがなブロックには対応する文字がない (U+3094 `ゔ` はあるが、IMEで打ちにくい)。今回の実装では `_KATAKANA_END = 0x30F6` まで対象、`ヴ` は U+30F4 で範囲内なので `ゔ` に変換される。これで OK か、特例で `ヴ` だけ素通しすべきか質問
- **半角カナ**: NFKC で全角に変換されてから katakana→hiragana に流れる想定。テストケースで `ｶﾀｶﾅ` → `かたかな` を確認したい
- **濁点・半濁点の分解**: NFKC は基本的に合成形 (NFC) を保つが、稀に decomposed 形 (`カ` + 濁点) で来る場合がある。`unicodedata.normalize("NFKC", ...)` で吸収されるはずだが、念のためテストで確認

## 7. 補足

### 設計の意図

- **標準ライブラリ縛り**: 「LangChain 不使用、自前実装」アピールに直結。外部依存ゼロを履歴書で書ける
- **`NormalizerOptions` を frozen dataclass**: 中間状態を持たないので Hashable、Streamlit の `st.cache_resource` でキャッシュ可能
- **`Normalizer` クラスと `normalize_text` 関数の二段提供**: ユーザーは設定不要なら関数 1 行、複雑な制御をしたければクラスを使う
- **適用は Day 9 で行う**: spec_009 で `loader.py` と `search.py` に注入、本日は単体実装と単体テストに集中

### Day 9 連携

- `loader.py` の Document に `normalized_body` フィールドを追加するか、search 側で query を正規化するか、両方やるか — Day 9 で決める。CC は Day 9 spec を読むまで自走しない
