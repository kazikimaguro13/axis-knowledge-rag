# spec_029: BM25 ハイブリッド検索 (3-way fusion: axis + vector + BM25)

- **Author**: Cowork (中島)
- **Created**: 2026-05-13
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Type**: feature (v0.6 候補、新規モジュール追加)
- **Bundles**: なし (v0.5 リリース後の単発機能拡張)

## 1. 目的

現在の検索は **軸フィルタ + ベクトル類似度** の 2-way hybrid。これに **BM25 (キーワード語彙的一致)** を加えて 3-way fusion にする。

```
[現状の弱点]
- 固有名詞検索が弱い (e.g. "ChromaDB" "FastAPI") - 単語をベクトル空間に押し込むと
  「データベース」「ウェブAPI」と意味的に近づきすぎ、希望のドキュメントが top_k に入りづらい
- LLM 関係者 (採用面接官など) が「BM25 と組み合わせている?」と聞いた時に
  「ベクトルだけです」と答えるのは v0.6 でカバーしたい

[変更後]
- BM25 score を vector score と同重みで合算 (RRF または重み付き和)
- axis filter は最初に効いてサブセットを作る (今と同じ)
- bm25 重みは検索クエリ時に指定可能 (デフォルト 0.5)
- 結果として recall@k が改善 (ベンチマークは spec_030 で別途)
```

## 2. 制約

### 触ってよいファイル

- `backend/src/bm25_index.py` — **新規**。トークナイザ + BM25 計算
- `backend/src/search.py` — `SearchEngine.search()` に bm25 fusion 追加、`bm25_weight` パラメータ追加
- `backend/tests/test_search.py` — 新規テスト追加
- `backend/tests/test_bm25_index.py` — **新規**
- `pyproject.toml` — `rank-bm25>=0.2.2` 依存追加
- `docs/design-decisions.md` — ADR-016 追加 (BM25 fusion)
- `docs/search-fusion.md` — **新規**。3-way hybrid の説明
- `mcp_server/schemas.py` — `SearchInput` に `bm25_weight: float = 0.5` 追加
- `mcp_server/server.py` — `axis_search` tool で `bm25_weight` を伝搬
- `CHANGELOG.md` — Day 29 追記

### 触ってはいけないもの

- `embedder.py` / `vector_store.py` / `normalizer.py` のロジック
- `rag.py` (RAG 側は変更なし、search が返す結果を使うだけ)
- `frontend/` (UI は v0.7 で対応、まずバックエンドのみ)
- `_ai_workspace/`

### コーディングルール

- `rank-bm25` の `BM25Okapi` を採用 (BM25L / BM25Plus との比較は ADR で言及)
- BM25 index は **インメモリ** に保持 (永続化は v0.7 で検討)
- トークナイザは形態素解析を使わず、**正規化済みテキストの文字 n-gram (n=1,2)** で済ます (依存削減、日本語精度はそれなりに出る)
- ruff + pytest 緑必須

## 3. やってほしいこと

### 3-1. `backend/src/bm25_index.py` 新規

```python
"""BM25 keyword index for hybrid search.

Builds an in-memory BM25 (Okapi) index over normalized document bodies.
Tokenization is character n-gram (n=1, 2) on normalized text — avoids
the morphological analyzer dependency while still being usable for
Japanese (full-word vocabulary matching).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from backend.src.normalizer import Normalizer

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    """Character n-gram tokenizer (n=1, 2) over already-normalized text.

    Examples:
        "あいう" -> ["あ", "い", "う", "あい", "いう"]
    """
    if not text:
        return []
    tokens: list[str] = []
    tokens.extend(text)  # n=1
    for i in range(len(text) - 1):
        tokens.append(text[i : i + 2])  # n=2
    return tokens


@dataclass
class BM25Index:
    """In-memory BM25 index over a fixed corpus."""

    doc_ids: list[str]
    normalizer: Normalizer
    _model: BM25Okapi

    @classmethod
    def build(cls, docs: list[tuple[str, str]], normalizer: Normalizer) -> BM25Index:
        """Build from `(doc_id, normalized_body)` pairs."""
        ids = [d[0] for d in docs]
        tokenized = [_tokenize(d[1]) for d in docs]
        if not tokenized:
            tokenized = [[""]]  # rank_bm25 needs non-empty corpus
        model = BM25Okapi(tokenized)
        logger.info("BM25Index built (n_docs=%d)", len(ids))
        return cls(doc_ids=ids, normalizer=normalizer, _model=model)

    def score(self, query: str) -> dict[str, float]:
        """Return {doc_id: bm25_score} for the (already-normalized) query."""
        q_tokens = _tokenize(self.normalizer(query))
        if not q_tokens:
            return {}
        scores = self._model.get_scores(q_tokens)
        # Min-max normalize to [0, 1] so it can be summed with cosine
        if not len(scores):
            return {}
        s_min = float(scores.min())
        s_max = float(scores.max())
        if s_max - s_min < 1e-9:
            return {d: 0.0 for d in self.doc_ids}
        norm_scores = (scores - s_min) / (s_max - s_min)
        return {d: float(s) for d, s in zip(self.doc_ids, norm_scores, strict=True)}

    def __len__(self) -> int:
        return len(self.doc_ids)
```

### 3-2. `backend/src/search.py` 更新

- `SearchEngine.__init__` に `bm25_index: BM25Index | None = None` パラメータ追加 (lazy build も可)
- `SearchEngine.search()` に `bm25_weight: float = 0.5` パラメータ追加
- fusion ロジック:

```python
def search(self, query, filters=None, top_k=5, bm25_weight=0.5):
    # 1. axis filter で候補絞り込み (今と同じ)
    where = _build_where_norm(...)
    
    # 2. vector search で top_k * 2 個取得 (BM25 と合流するため広めに)
    over_fetch = max(top_k * 2, 20)
    vec_results = self._store.query(self._embedder(query), where=where, top_k=over_fetch)
    
    # 3. BM25 score を vec_results の id 集合だけ計算
    if self._bm25_index is not None and bm25_weight > 0.0:
        bm25_scores = self._bm25_index.score(query)
    else:
        bm25_scores = {}
    
    # 4. weighted sum で再ランキング
    fused = []
    for r in vec_results:
        bm25 = bm25_scores.get(r.id, 0.0)
        final = (1 - bm25_weight) * r.score + bm25_weight * bm25
        fused.append((r, final))
    fused.sort(key=lambda x: -x[1])
    
    # 5. top_k で打ち切り、SearchResult を返す (score は fused 値に更新)
    return [
        SearchResult(..., score=final)
        for r, final in fused[:top_k]
    ]
```

- `bm25_weight=0.0` の時は完全に従来挙動 (vector only) になるよう保証

### 3-3. `mcp_server/schemas.py` 更新

`SearchInput` に追加:

```python
bm25_weight: float = Field(
    default=0.5,
    ge=0.0,
    le=1.0,
    description="Weight of BM25 score in hybrid fusion (0.0 = vector only, 1.0 = BM25 only)"
)
```

### 3-4. `mcp_server/server.py` 更新

`axis_search` tool の本文で `params.bm25_weight` を `engine.search(...)` に伝搬。docstring も更新。

### 3-5. テスト追加

`backend/tests/test_bm25_index.py` 新規:

```python
def test_bm25_index_basic_scoring():
    normalizer = Normalizer.identity()
    idx = BM25Index.build(
        [
            ("doc_001", "chromadb の永続化設計について"),
            ("doc_002", "fastapi で軸検索 api を作る"),
            ("doc_003", "RAG パイプラインの設計判断"),
        ],
        normalizer,
    )
    scores = idx.score("chromadb")
    assert scores["doc_001"] > scores["doc_002"]
    assert scores["doc_001"] > scores["doc_003"]


def test_bm25_index_empty_query_returns_empty_dict():
    idx = BM25Index.build([("doc_001", "本文")], Normalizer.identity())
    assert idx.score("") == {}


def test_bm25_index_no_matches_returns_zero():
    idx = BM25Index.build([("doc_001", "本文")], Normalizer.identity())
    scores = idx.score("まったく関係ないクエリ")
    # 全部 0 でも OK、min-max norm 後の最小値が 0
    assert all(0.0 <= v <= 1.0 for v in scores.values())
```

`backend/tests/test_search.py` に追加:

```python
def test_search_bm25_weight_0_matches_vector_only():
    """bm25_weight=0.0 で従来挙動 (vector only) と完全一致するか"""
    # 同じクエリで bm25_weight=0.0 と bm25 無し設定で結果が一致

def test_search_bm25_weight_1_orders_by_keyword_match():
    """bm25_weight=1.0 で完全 BM25 ランキングになるか"""

def test_search_bm25_changes_ranking():
    """bm25_weight が 0 と 0.5 で順位が変わるケースを 1 つ用意"""
```

`mcp_server/tests/test_server.py` に追加:

```python
async def test_axis_search_with_bm25_weight():
    """SearchInput(bm25_weight=0.7) が server を通して engine.search に渡るか"""
```

### 3-6. `docs/design-decisions.md` に ADR-016 追加

```markdown
## ADR-016: BM25 を加えて 3-way hybrid 検索にする

- **Date**: 2026-05-13
- **Status**: Accepted

### Context
v0.5 までの hybrid は (a) 軸フィルタ + (b) ベクトル類似度の 2-way。
ベクトルは意味的近接に強いが、**固有名詞 / 厳密な単語マッチ** に弱い。
"ChromaDB" を検索しても「データベース」「ベクトルストア」が並ぶ。

### Decision
- BM25Okapi (rank_bm25) を採用、in-memory index
- 文字 n-gram (n=1,2) でトークナイズ (形態素解析依存を避ける)
- vector score (cosine) と BM25 score (min-max 正規化) を weighted sum
- bm25_weight=0.5 デフォルト、API/MCP から上書き可

### Consequences
- ✅ 固有名詞検索が強くなる
- ✅ ベクトルだけだと埋もれる希少語が浮上
- ❌ BM25 index がメモリに乗る (1000 docs で ~MB オーダー、無視できる)
- ❌ index 再構築が必要 (ingester で文書追加した時)
- ❌ 文字 n-gram は形態素ベース BM25 より精度が劣る (許容、複雑性とのトレードオフ)

### Alternatives Considered
- **SPLADE / ColBERT**: sparse-dense 学習モデル。実装重い、v1.0 候補
- **Elasticsearch / OpenSearch**: 外部依存、Local-first の方針に反する
- **形態素解析 (MeCab / Sudachi)**: 辞書配布が重い、初期セットアップを増やしたくない
- **重み付き和ではなく RRF (Reciprocal Rank Fusion)**: 検討したが、score 値が直感的でない。重み付き和の方が「ベクトル寄り / BM25 寄り」を説明しやすいので採用
```

### 3-7. `docs/search-fusion.md` 新規

3-way fusion の図解 + bm25_weight チューニングガイド。

```markdown
# 3-way hybrid search

## アーキテクチャ図

```
ユーザクエリ
    ↓ normalizer
正規化クエリ
    ↓
┌───────────────────────────────────────────────────┐
│ 1. 軸フィルタ (where 句, Chroma 内)               │
│    {category: "技術記事"} など → サブセット作成   │
└───────────────────────────────────────────────────┘
    ↓ 候補ドキュメント集合
┌─────────────────┐ ┌─────────────────┐
│ 2a. Vector      │ │ 2b. BM25        │
│    Embedder →   │ │    n-gram →     │
│    cosine sim   │ │    BM25Okapi    │
│    score [0,1]  │ │    score [0,1]  │
└─────────────────┘ └─────────────────┘
            ↓             ↓
       ┌─────────────────────┐
       │ 3. Weighted Fusion  │
       │ final = (1-w)*vec   │
       │       +     w*bm25  │
       └─────────────────────┘
            ↓
        top_k で打ち切り
```

## bm25_weight チューニング

| 値 | 用途 |
|---|---|
| 0.0 | ベクトル単独 (v0.5 互換) |
| 0.3 | 意味検索メインだが固有名詞も拾いたい |
| 0.5 | 中庸 (デフォルト) |
| 0.7 | 固有名詞メイン、意味検索は補助 |
| 1.0 | BM25 単独 (デバッグ・比較用) |
\```
```

### 3-8. `pyproject.toml`

`dependencies` に追加:
```
"rank-bm25>=0.2.2",
```

### 3-9. `CHANGELOG.md` Day 29

```markdown
### Day 29 (2026-05-XX) — 3-way hybrid search

- backend/src/bm25_index.py: 新規、BM25Okapi + n-gram トークナイザ
- backend/src/search.py: SearchEngine に bm25_weight 追加、weighted fusion
- mcp_server: SearchInput.bm25_weight 追加、axis_search 経由で伝搬
- docs/design-decisions.md: ADR-016 追加
- docs/search-fusion.md: 新規
- tests: 新規 7 件 (bm25_index 3 + search 3 + mcp 1)
- 後方互換: bm25_weight=0.0 で v0.5 と同じ挙動
```

### 3-10. 動作確認

```bash
cd ~/projects/axis-knowledge-rag
pip install -e . --break-system-packages

# ruff
ruff check .

# pytest
pytest --quiet
pytest backend/tests/test_bm25_index.py -v
pytest backend/tests/test_search.py -k bm25 -v

# 既存テストが全て緑のままか確認
pytest --quiet  # 全 162+ 件 PASS
```

### 3-11. コミット粒度

1. `feat(search): add BM25Index with character n-gram tokenizer`
2. `feat(search): wire BM25 into SearchEngine with weighted fusion`
3. `feat(mcp): expose bm25_weight in axis_search tool`
4. `test: cover BM25Index and hybrid fusion scenarios`
5. `docs: add ADR-016 + search-fusion.md`
6. `docs: changelog Day 29 + bump pyproject deps`

`git push -u origin feat/spec_029-bm25-hybrid`

## 4. 成功条件

- [ ] `BM25Index` が builds + scores 正常動作
- [ ] `SearchEngine.search(bm25_weight=0.0)` で v0.5 と完全同じ結果
- [ ] `SearchEngine.search(bm25_weight=0.5)` で順位が変わるテストケースが PASS
- [ ] MCP `axis_search` tool で `bm25_weight` を受け取れる
- [ ] 全 pytest 緑 (162+ 件)
- [ ] ruff 緑
- [ ] CI 緑
- [ ] ADR-016 + search-fusion.md がリンク切れなしで docs/INDEX.md から辿れる

## 5. 出力先

`~/projects/axis-knowledge-rag/_ai_workspace/bridge/outbox/result_029.md`

## 6. 補足

### main HEAD

`483643e chore(release): bump to 0.5.0 + add live CI badges`

### 後続の spec 候補 (v0.6 完成形)

- **spec_030**: BM25 vs vector-only のベンチマーク (recall@k / MRR、testset 50 件作成)
- **spec_031**: BM25 index の永続化 (pickle or sqlite)
- **spec_032**: フロントエンド UI で bm25_weight スライダー追加

### tokenizer の選択について

形態素解析 (MeCab/Sudachi) を選ばなかった理由は ADR-016 に記載。
将来「精度を上げたい」となった時の差し替え戦略:
- `_tokenize` を `Tokenizer` クラス化、interface を切る
- `MeCabTokenizer` / `NgramTokenizer` を選べる構造に
- ただし v0.6 では n-gram で出荷 (依存最小、十分使える)
