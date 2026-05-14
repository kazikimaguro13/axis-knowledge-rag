# result_029: BM25 ハイブリッド検索 (3-way fusion)

- **Spec**: `inbox/spec_029.md`
- **Executor**: Claude Code (`dev-b`)
- **Started**: 2026-05-14
- **Finished**: 2026-05-14
- **Status**: done
- **Branch**: `feat/spec_029-bm25-hybrid` (pushed to origin)
- **HEAD**: `4b4e5d1 docs: changelog Day 29 + bump pyproject deps`

## 1. 要約

軸フィルタ + ベクトル類似度の 2-way hybrid に **BM25 (rank_bm25 / Okapi)** を加えて
**3-way fusion** にした。トークナイザは形態素解析を避けて **文字 n-gram (n=1, 2)** を採用、
BM25 score を min-max 正規化して cosine と weighted sum で合算する。`bm25_weight=0.5` を
デフォルトに、`SearchInput.bm25_weight` と CLI `--bm25-weight` から上書きできる。

**`bm25_weight=0.0` で v0.5 と完全同一の結果になる** ことをテストで verify。MCP サーバの
`axis_search` tool も `bm25_weight` を受け付けて `SearchEngine.search()` まで forward する
配線まで完了 (spy テストで確認)。なお MCP サーバ側で `BM25Index.build(...)` を `_get_engine()`
に挿す配線は spec_030 に残してある (現状の MCP は `bm25_weight` を受理しつつ no-op、
スキーマだけ先に固める形)。

最終確認:
- `ruff check .` → **All checks passed**
- `pytest` → **169 passed in 25.42s** (旧 155 件 → +14 件: bm25_index 8 + search 5 + mcp 1)
- 既存テストの regression ゼロ

## 2. 変更ファイル一覧

| ファイル | 種別 | 概要 |
|---|---|---|
| `backend/src/bm25_index.py` | 新規 | `BM25Okapi` + 文字 n-gram(1,2) tokenizer / min-max norm |
| `backend/src/search.py` | 更新 | `SearchEngine.__init__(bm25_index=...)` + `search(bm25_weight=0.5)` + CLI |
| `backend/src/normalizer.py` | 更新 | `Normalizer.identity()` classmethod 追加 (pass-through) |
| `mcp_server/schemas.py` | 更新 | `SearchInput.bm25_weight: float` (ge=0, le=1, default=0.5) |
| `mcp_server/server.py` | 更新 | `axis_search` が `bm25_weight` を `engine.search` に forward、docstring 更新 |
| `backend/tests/test_bm25_index.py` | 新規 | 8 件 |
| `backend/tests/test_search.py` | 更新 | bm25 fusion テスト 5 件追加 |
| `mcp_server/tests/test_server.py` | 更新 | `test_axis_search_with_bm25_weight` 1 件追加 |
| `docs/design-decisions.md` | 更新 | ADR-016 追加 |
| `docs/search-fusion.md` | 新規 | 3-way fusion アーキ図 / tuning ガイド |
| `docs/INDEX.md` | 更新 | ADR 件数 15→16、search-fusion.md エントリ追加 |
| `pyproject.toml` | 更新 | `rank-bm25>=0.2.2` 追加 |
| `CHANGELOG.md` | 更新 | Day 29 エントリ |

## 3. コミット履歴 (6 件)

```
4b4e5d1 docs: changelog Day 29 + bump pyproject deps
d82b35d docs: add ADR-016 + search-fusion.md
c45edb7 test: cover BM25Index and hybrid fusion scenarios
310f917 feat(mcp): expose bm25_weight in axis_search tool
b7208f9 feat(search): wire BM25 into SearchEngine with weighted fusion
beaa359 feat(search): add BM25Index with character n-gram tokenizer
```

`git push -u origin feat/spec_029-bm25-hybrid` 済み。
PR URL は GitHub のヒント通り `https://github.com/kazikimaguro13/axis-knowledge-rag/pull/new/feat/spec_029-bm25-hybrid`。

## 4. 設計上の補足

### 4-1. `bm25_weight=0.0` の互換性保証

`SearchEngine.search()` 内に `use_bm25 = (query is not None and self._bm25_index is not None and bm25_weight > 0.0)` という flag を置き、`use_bm25=False` のときは v0.5 と同じパス
(over-fetch なし、fusion ループなし) に流す。これによって:

- `bm25_weight=0.0` → v0.5 と byte-identical な結果
- `bm25_index=None` → 旧テストはまったく改修不要

テスト `test_search_bm25_weight_0_matches_vector_only` で `[r.id for r in vec_only] == [r.id for r in fused_0]` と `score ≈` を assert している。

### 4-2. Over-fetch (top_k × 2)

fusion が有効なときに vector top_k だけ取って BM25 で並べ替えると、「vector top_k には
入らなかったが BM25 で上位にくるはずだったドキュメント」が消える。`max(top_k * 2, 20)` で
広めに vector から取って fusion 後に top_k へ切る。

### 4-3. BM25 IDF と corpus サイズ

`BM25Okapi` は `idf = log(N - df + 0.5) - log(df + 0.5)` を使うため、`N=2` で `df=1` のとき
IDF=0 になる退化ケースがある (テスト書き始めで 1 度踏んだ)。実運用 (knowledge base 数十〜
数千件) では発生しないが、テスト fixture は **3 件以上** で構成している。

### 4-4. MCP サーバ側の現状

`mcp_server/server.py._get_engine()` ではまだ `BM25Index.build(...)` を呼んでいない。
理由:

1. MCP サーバ起動時の全文取得経路 (`VectorStore` から body を取り出す) が未整備
2. spec_029 のスコープは「BM25 fusion をバックエンドに入れる + MCP 公開 API を固める」
3. `bm25_weight` を受理しつつ no-op (= 現状 v0.5 互換挙動) で安全

spec_030 で `_get_engine()` 配線 + recall@k ベンチマークをセットで入れる予定。
spec_029 でも `axis_search` 経由で `engine.search(..., bm25_weight=0.7)` まで渡る
こと自体は spy テストで確認済み。

### 4-5. `Normalizer.identity()` の追加理由

spec 本文のテストコードが `Normalizer.identity()` を前提にしていたため classmethod として
追加。`NormalizerOptions(nfkc=False, katakana_to_hiragana=False, lowercase=False)` を返す
pass-through。テスト中で「入力がすでに正規化済み」と明示するために使うのが想定用途。
既存ロジックには影響なし。

## 5. テスト内訳

### 5-1. `backend/tests/test_bm25_index.py` (新規 8 件)

- `test_tokenize_character_ngrams` — n=1+n=2 を生成
- `test_tokenize_empty_returns_empty_list`
- `test_bm25_index_basic_scoring` — `chromadb` クエリで該当 doc が最上位
- `test_bm25_index_empty_query_returns_empty_dict`
- `test_bm25_index_no_matches_returns_normalized_scores` — `[0, 1]` 範囲を保つ
- `test_bm25_index_len_matches_corpus`
- `test_bm25_index_uses_normalizer_for_query` — "ChromaDB" → "chromadb" 経由でヒット
- `test_bm25_index_single_doc_corpus` — degenerate min-max を 0.0 として処理

### 5-2. `backend/tests/test_search.py` (+5 件)

- `test_search_bm25_weight_0_matches_vector_only` — id/score 完全一致
- `test_search_bm25_weight_1_orders_by_keyword_match` — BM25 only で keyword match doc が top
- `test_search_bm25_changes_ranking` — 0.5 fusion が top を BM25 match に押し上げる
- `test_search_bm25_weight_ignored_when_no_index` — `bm25_index=None` で全 weight に対し no-op
- `test_search_axis_only_ignores_bm25` — `query=None` で BM25 を short-circuit

### 5-3. `mcp_server/tests/test_server.py` (+1 件)

- `test_axis_search_with_bm25_weight` — `monkeypatch` で `engine.search` を spy、
  `SearchInput(bm25_weight=0.7)` が `engine.search(bm25_weight=0.7)` まで forward することを確認

## 6. 成功条件チェック

- [x] `BM25Index` が builds + scores 正常動作
- [x] `SearchEngine.search(bm25_weight=0.0)` で v0.5 と完全同じ結果 (id/score)
- [x] `SearchEngine.search(bm25_weight=0.5)` で順位が変わる test case が PASS
- [x] MCP `axis_search` tool で `bm25_weight` を受け取れる (forward まで verify)
- [x] 全 pytest 緑 (169 件、旧 155 件 + 14 件)
- [x] ruff 緑
- [ ] CI 緑 — push 直後。GitHub Actions は走るが、本 result 提出時点では実行中の可能性あり
- [x] ADR-016 + search-fusion.md がリンク切れなしで docs/INDEX.md から辿れる

## 7. 後続 spec 候補 (v0.6 完成形)

spec 本文の v0.6 ロードマップを踏襲:

- **spec_030**: MCP サーバの `_get_engine()` に `BM25Index.build(...)` を配線 +
  recall@k / MRR ベンチマーク (testset 50 件、bm25_weight grid search)
- **spec_031**: BM25 index の永続化 (pickle or sqlite、ingester 連動)
- **spec_032**: フロントエンド UI に `bm25_weight` スライダーを追加

## 8. 既知の制約 / TODO

1. **MCP サーバが BM25 を build せずに起動する** — `bm25_weight` パラメータはスキーマ
   レベルで受理されるが、現状の MCP は no-op (= v0.5 互換挙動)。spec_030 で本格配線。
   後方互換の観点ではこれで OK (パラメータ追加だけで先にスキーマを固める判断)。
2. **`Normalizer.identity()` を後で減らす可能性** — テストの可読性のために入れたが、
   `Normalizer()` で代替可能なケースが多い。リファクタ余地あり (機能影響なし)。
3. **BM25 IDF=0 の退化ケース** — corpus サイズが 2 で `df=1` の term は IDF=0 になる。
   実運用 (数百件超) では発生しないが、ベンチマーク testset を作る spec_030 では
   corpus 規模を意識する必要がある。
