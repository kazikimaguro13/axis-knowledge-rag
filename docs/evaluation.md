# Evaluation ガイド

本ドキュメントでは、axis-knowledge-rag の RAGAS 自動評価システムについて解説する。

## 目的

v0.6.0 まで検索品質の改善は「手動サンプル確認」に頼っていた。v0.7.0 から LLM-as-a-Judge による自動評価を CI に組み込み、**PR ごとに品質変動を数値で可視化**する。

## アーキテクチャ概要

```
GitHub PR / nightly cron
        │
        ▼
.github/workflows/ragas.yml
        │
        ▼
evaluation/run_ragas.py
    ├── qa_v1.json (25 件 QA)
    ├── backend.src.search (SearchEngine)
    ├── backend.src.rag (RAGPipeline)
    └── evaluation/judge.py (Gemini Flash)
        │
        ▼
ragas.evaluate(faithfulness / answer_relevancy / context_precision / context_recall)
        │
        ▼
evaluation/runs/ci-<sha>.json  ← 実行結果
evaluation/baseline.json       ← nightly 更新
PR コメント                     ← メトリクス diff 表示
```

## データセット仕様 (`qa_v1.json`)

### 構成

25 件の QA ペア。`examples/knowledge/01-05.md` のコンテンツをカバーする。

| 種別 | 件数 | 説明 |
|---|---|---|
| 定義系 | 5 | 「〜とは何か？」 |
| 比較系 | 5 | 「A と B の違いは？」 |
| Why 系 | 5 | 「なぜ〜？」 |
| How 系 | 5 | 「〜するにはどうするか？」 |
| エッジケース | 5 | axes フィルタ込み、または知識ベース外の質問 |

### 対象ドキュメント

| ドキュメント | カバーする QA |
|---|---|
| `01-rag-patterns.md` (doc_001) | qa_001, qa_006, qa_011, qa_016, qa_020 |
| `02-vector-search.md` (doc_002) | qa_002, qa_007, qa_012, qa_017, qa_024 |
| `03-yaml-frontmatter.md` (doc_003) | qa_003, qa_008, qa_013, qa_018, qa_023 |
| `04-claude-skills.md` (doc_004) | qa_004, qa_009, qa_014 |
| `05-prompt-engineering.md` (doc_005) | qa_005, qa_010, qa_015, qa_019, qa_022 |
| エッジケース (axes フィルタ / 存在しない情報) | qa_021, qa_022, qa_023, qa_025 |

### JSON スキーマ

```json
{
  "id": "qa_001",
  "question": "...",
  "ground_truth": "...",
  "expected_contexts": ["01-rag-patterns.md"],
  "axes": null
}
```

- `ground_truth`: 100〜300 字の期待回答
- `expected_contexts`: 期待出典ファイル (評価参考、ragas には渡さない)
- `axes`: null = 全文書対象、dict = axis フィルタあり

## メトリクス解説

### faithfulness

生成回答が retrieved context に忠実かを測る。context にない内容を断言するとスコアが下がる（ハルシネーション検出）。

計算: 回答中の各主張が context に支持されているか Gemini Flash が判定。

### answer_relevancy

質問に対して回答がどれだけ関連しているかを測る。回答が質問からズレている・冗長すぎる場合に下がる。

計算: 回答から逆に質問を生成し、元の質問とコサイン類似度を計算（embeddings 使用）。

### context_precision

取得した context のうち、実際に回答に必要なものの割合。不必要な文書が上位に混じるとスコアが下がる。

計算: 各取得文書が ground_truth に関連するか Gemini Flash が評価し、ランク重み付き precision を計算。

### context_recall

ground_truth を裏付けるために必要な情報が、取得した context に含まれているかを測る。関連文書を取得し損ねるとスコアが下がる。

計算: ground_truth の各要素が context でカバーされているか Gemini Flash が判定。

## Judge 選定理由

### Gemini 1.5 Flash を採用

- 本プロジェクトは Gemini API を Embedder として既存活用。同一 API キーで judge を走らせられるため運用コストが低い
- GPT-4 と比べてコストが約 1/10
- 温度 0.0 設定で deterministic に近い動作
- 詳細は [ADR-019](adr/ADR-019-ragas-evaluation.md) 参照

### Embeddings: `text-embedding-004`

- Embedder と同一モデルで一貫性がある
- `answer_relevancy` / `context_precision` / `context_recall` の埋め込み計算に使用

## baseline.json

```json
{
  "timestamp": "2026-05-14T00:00:00Z",
  "git_sha": "abc1234",
  "dataset": "evaluation/datasets/qa_v1.json",
  "scores": {
    "faithfulness": 0.87,
    "answer_relevancy": 0.85,
    "context_precision": 0.79,
    "context_recall": 0.82
  }
}
```

nightly CI が更新してコミット。初回は bootstrap 値 (0.0) でコミットし、最初の nightly 実行後に実スコアで上書きされる。

## 回帰閾値

- v0.7: `--regression-threshold 0.05` (5% 低下で WARN、exit 0)
- v0.8 予定: exit 1 で PR をブロック

stochastic ノイズを考慮し、初週の CI 実行結果を見ながら 5〜10% の範囲で調整する。

## コスト

| 条件 | 推定 |
|---|---|
| judge calls / run | ~100 (25 件 × 4 メトリクス) |
| Gemini Flash 単価 | ~$0.0005 / 1K tokens |
| コスト / run | ~$0.05 |
| nightly 30 runs / 月 | ~$1.5 / 月 |

## ローカル実行方法

```bash
# セットアップ
pip install -e ".[eval]"

# 通常実行
make eval

# baseline 更新
make eval-update-baseline

# smoke test (3 件のみ)
jq '.items |= .[0:3]' evaluation/datasets/qa_v1.json > /tmp/qa_smoke.json
python -m evaluation.run_ragas \
  --dataset /tmp/qa_smoke.json \
  --baseline evaluation/baseline.json \
  --output /tmp/smoke.json
cat /tmp/smoke.json | jq .scores
```

## 将来の拡張

| spec | 内容 |
|---|---|
| spec_036 (v0.8) | regression で exit 1 に変更、PR ブロック化 |
| spec_037 (v0.8) | qa_v2.json (50 件、多言語対応) |
| spec_038 (v0.8) | A/B フラグ: parent_doc.enabled true/false 並列比較 |
| spec_039 (v0.8) | GitHub Pages でスコア推移グラフ公開 |
