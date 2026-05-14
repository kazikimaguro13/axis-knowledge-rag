# evaluation/

RAGAS を使った自動評価パッケージ。検索品質と RAG 生成品質を LLM-as-a-Judge で定量測定し、CI で回帰を自動検出する。

## ディレクトリ構成

```
evaluation/
├── __init__.py
├── judge.py              # Gemini 1.5 Flash LLM judge wrapper
├── run_ragas.py          # メイン評価ランナー
├── baseline.json         # 直近の基準スコア (CI が nightly で更新)
├── requirements.txt      # eval 専用依存 (ragas / datasets / langchain-google-genai)
├── datasets/
│   └── qa_v1.json        # 25 件 QA データセット
└── runs/                 # 実行ごとのスコア JSON (gitignore 対象)
```

## セットアップ

```bash
pip install -e ".[eval]"
```

## ローカル実行

```bash
# 通常実行 (baseline と比較して回帰を WARN)
make eval

# baseline を更新する場合
make eval-update-baseline

# 煙テスト (3 件のみ)
jq '.items |= .[0:3]' evaluation/datasets/qa_v1.json > /tmp/qa_smoke.json
python -m evaluation.run_ragas \
  --dataset /tmp/qa_smoke.json \
  --baseline evaluation/baseline.json \
  --output /tmp/smoke.json
cat /tmp/smoke.json | jq .scores
```

## 評価メトリクス

| メトリクス | 説明 | judge |
|---|---|---|
| `faithfulness` | 生成回答が retrieved context に忠実か | Gemini Flash |
| `answer_relevancy` | 質問に対する回答の妥当性 | Gemini Flash + embeddings |
| `context_precision` | 取得 context のうち真に必要な割合 | Gemini Flash + embeddings |
| `context_recall` | 正答を裏付ける context を取得できた割合 | Gemini Flash + embeddings |

## CI

- **nightly**: 毎日 03:00 JST に全 25 件を実行し baseline を自動更新
- **PR トリガー**: `backend/src/search.py` / `rag.py` / `chunker.py` / `bm25*.py` / `evaluation/**` / `config.yml` の変更時にスコアを PR コメントとして投稿

詳細: [`.github/workflows/ragas.yml`](../.github/workflows/ragas.yml) / [`docs/evaluation.md`](../docs/evaluation.md)

## データセット仕様

`datasets/qa_v1.json` は 25 件の QA ペアで構成。各 item の形式:

```json
{
  "id": "qa_001",
  "question": "...",
  "ground_truth": "...",
  "expected_contexts": ["01-rag-patterns.md"],
  "axes": null
}
```

- `expected_contexts`: 期待される出典ファイル (評価参考用、ragas には渡さない)
- `axes`: axis フィルタ。null は全文書が対象

## 回帰閾値

v0.7 では **WARN only** (exit 0)。`--regression-threshold 0.05` で 5% 以上の低下を警告。
v0.8 で block 化検討 (ADR-019 参照)。
