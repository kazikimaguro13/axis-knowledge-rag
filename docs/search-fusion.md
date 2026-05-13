# 3-way hybrid search

axis-knowledge-rag v0.6 の検索パイプライン。**軸フィルタ + ベクトル類似度 + BM25**
を組み合わせ、構造化・意味的・語彙的の 3 つの観点から retrieval する。

関連 ADR: [ADR-016](design-decisions.md#adr-016-bm25-を加えて-3-way-hybrid-検索にする)

---

## アーキテクチャ図

```
ユーザクエリ
    │ normalizer (NFKC + kata→hira + lowercase)
    ▼
正規化クエリ
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 1. 軸フィルタ (Chroma where 句)                     │
│    {category: "技術記事"} など → サブセット作成     │
└─────────────────────────────────────────────────────┘
    │ 候補ドキュメント集合 (top_k * 2 で over-fetch)
    │
    ├─────────────────────┬─────────────────────┐
    ▼                     ▼                     │
┌─────────────────┐ ┌─────────────────┐         │
│ 2a. Vector      │ │ 2b. BM25        │         │
│  Embedder →     │ │  n-gram (n=1,2) │         │
│  cosine sim     │ │  BM25Okapi      │         │
│  score [0, 1]   │ │  min-max [0, 1] │         │
└─────────────────┘ └─────────────────┘         │
            │             │                     │
            ▼             ▼                     │
       ┌─────────────────────┐                  │
       │ 3. Weighted Fusion  │                  │
       │ final =             │                  │
       │   (1-w) * vec       │                  │
       │ +     w * bm25      │                  │
       └─────────────────────┘                  │
                  │                             │
                  ▼                             │
              top_k で打ち切り ◄─────────────────┘
```

- 軸フィルタは **そのまま素通し** で候補を絞る (Chroma の where 句で実現)
- BM25 と vector はそれぞれ独立にスコアを出し、`bm25_weight` で重みづけ加算
- `bm25_weight=0.0` のときは v0.5 互換 (vector only)。BM25 index 計算はスキップ

---

## bm25_weight チューニング

| 値    | 用途                                                          |
| ----- | ------------------------------------------------------------- |
| `0.0` | ベクトル単独 (v0.5 互換、A/B 比較のベースライン)              |
| `0.3` | 意味検索メイン、固有名詞も多少拾いたい                        |
| `0.5` | 中庸 (デフォルト)。バランス重視                               |
| `0.7` | 固有名詞・厳密語彙メイン、意味検索は補助                      |
| `1.0` | BM25 単独 (デバッグ / 比較用)                                 |

### どの値を選ぶか

- **製品検索 / ドキュメント検索** で固有名詞 (型番、API 名、人名) が重要なら `0.5–0.7`
- **概念検索 / FAQ** で言い換えが効くべきなら `0.2–0.4`
- 迷ったら `0.5` で出荷、運用ログから調整

---

## 設計上のポイント

### なぜ文字 n-gram トークナイザか

形態素解析 (MeCab / Sudachi) は精度が出るが、辞書配布が重い (`unidic-lite` で 50MB+)。
本プロジェクトの「Local-first、依存最小」方針と合わない。

文字 n-gram (n=1, 2) は

- 日本語 / 英語混在テキストで等しく機能する
- 辞書不要、追加依存ゼロ
- 固有名詞 (ChromaDB, FastAPI など) の部分一致が効く

精度面で形態素ベース BM25 に劣るが、固有名詞検索の改善という当初目的には十分。
将来 `Tokenizer` interface に分離して `MeCabTokenizer` を選べる構造にする余地は残してある
(v0.7+ ロードマップ)。

### なぜ Weighted Sum (RRF ではなく)

Reciprocal Rank Fusion も検討した。RRF は score の絶対値に依存せず堅牢だが、
**「ベクトル寄り / BM25 寄り」を 1 スカラーで説明できない**。UI で「半々で混ぜる」
「7:3 で固有名詞重視」と説明できる直感性を優先した。score の正規化さえ揃えれば、
weighted sum でも十分。

### Over-fetch (top_k × 2)

vector 検索だけで top_k を打ち切ってから BM25 で並べ替えると、BM25 で浮上すべき
ドキュメントが「vector top_k に入らなかった」という理由で消えてしまう。これを
避けるため、fusion 時は `max(top_k * 2, 20)` 件を vector から over-fetch して
BM25 と合流させてから top_k に切る。

### BM25 index と永続化

現状は **build_index 実行時に in-memory で構築**。サーバ再起動のたびに再構築される。
1000 docs 程度ではミリ秒オーダーで終わるので体感されないが、10K docs を超えたら
pickle / sqlite で永続化する (v0.7 候補、spec_031)。

---

## 利用例

### Python (backend.src.search)

```python
from backend.src.bm25_index import BM25Index
from backend.src.search import SearchEngine

bm25 = BM25Index.build(
    [(d.id, d.normalized_body) for d in docs],
    normalizer,
)
engine = SearchEngine(store, embedder, normalizer, bm25_index=bm25)
results = engine.search("ChromaDB の永続化", top_k=5, bm25_weight=0.5)
```

### CLI

```bash
python -m backend.src.search "ChromaDB" --top 5 --bm25-weight 0.7
```

### MCP

```json
{
  "tool": "axis_search",
  "input": {
    "query": "ChromaDB の永続化",
    "filters": {"category": "技術記事"},
    "top_k": 5,
    "bm25_weight": 0.7
  }
}
```

---

## 既知の制約

- BM25 index は **再起動時に再構築** (永続化未実装、v0.7 で対応予定)
- `axis-knowledge-rag` の MCP サーバは **現状 BM25 index を build せずに起動** している。
  `_get_engine()` 経由で `BM25Index.build(...)` を呼ぶ配線は spec_030 (Day 30) で追加予定。
  それまで `bm25_weight` パラメータはスキーマには存在するが no-op として安全に受理される
- 文字 n-gram の精度限界 — 同音異義語や複合語のチャンク境界は崩れる場合がある

---

## ベンチマーク

`recall@k` / `MRR` の定量評価は spec_030 で別途実施予定。testset 50 件を作成し、
`bm25_weight ∈ {0.0, 0.3, 0.5, 0.7, 1.0}` で grid search する。
