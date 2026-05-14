# ADR-019: RAGAS + Gemini Flash による自動評価 CI

- **Status**: Accepted
- **Date**: 2026-05-14
- **Author**: Nakashima

## Context

v0.6.0 までの開発では、検索品質の改善（軸フィルタ・BM25 ハイブリッドなど）を「手動サンプル 5〜10 件で確認した感覚」に頼っていた。この状況では：

- PR ごとに回帰が起きても気づけない
- 「精度が上がった」という主張に数値根拠がない
- ポートフォリオ・就職活動において説得力が弱い

自動評価パイプラインを CI に組み込み、**PR 単位で品質変動を数値で可視化**することを目的とする。

## Decision

**RAGAS フレームワーク + Gemini 1.5 Flash を LLM Judge として採用し、GitHub Actions に組み込む。**

- メトリクス: `faithfulness` / `answer_relevancy` / `context_precision` / `context_recall`
- データセット: `evaluation/datasets/qa_v1.json` (25 件 QA)
- Judge LLM: Gemini 1.5 Flash (`gemini-1.5-flash`)
- Judge Embeddings: Gemini `text-embedding-004` (本体と同一、コスト最小)
- baseline: `evaluation/baseline.json` (nightly で自動更新)
- CI トリガー: nightly (毎日 03:00 JST) + 関連ファイル変更 PR

## Alternatives Considered

### (a) OpenAI GPT-4 Judge
- 却下理由: コストが約 10 倍。本プロジェクトは Gemini API key 既存のため統一を優先。

### (b) BLEU / ROUGE
- 却下理由: これらは n-gram 一致率に基づき、自由記述 RAG 回答の品質指標として不適切。参照テキストの言い換えが多い日本語には特に合わない。

### (c) 自前 LLM Judge プロンプト
- 却下理由: RAGAS はオープンソースで実装が公開されており、他プロジェクトとの peer comparison が可能。自前実装では再現性と標準性に劣る。

### (d) Gemini 1.5 Flash-8B に降格
- 却下理由: Flash より 20-30% 品質が低く、faithfulness / context_recall の stochastic ノイズが大きくなりがち。judge コストは $0.05/run → $0.03/run の差に過ぎず、品質優先で Flash を維持。

## Consequences

### Positive
- PR ごとに RAGAS 4 メトリクスが数値化・比較されるため回帰を早期検出できる
- LLM-as-a-Judge を CI に組み込んだ実績はポートフォリオとして差別化要素になる
- baseline.json をコミット管理することで履歴追跡が可能

### Negative / Risks
- **judge コスト**: 25 件 × 4 metrics ≒ 100 judge call / run。Gemini Flash 料金換算で約 $0.05/run。nightly 30 回/月 = 約 $1.5/月
- **stochastic ノイズ**: LLM Judge は温度 0.0 でも若干ゆらぎ、5% 閾値での false alarm が発生しうる
- **GEMINI_API_KEY**: GitHub Secret 設定済みを前提。未設定時は run_ragas.py が RuntimeError を返す

### Mitigation
- v0.7 では `continue-on-error: true` かつ exit 0 で **WARN only**。誤検出実績を見てから閾値を 5〜10% の範囲で調整
- v0.8 で block 化（exit code 1）を検討。そのタイミングで本 ADR を update する

## Cost Estimation

| 項目 | 推定 |
|---|---|
| judge call / run | ~100 (25 items × 4 metrics) |
| Gemini Flash 料金 | ~$0.05 / run |
| nightly runs / 月 | 30 |
| 月額コスト | ~$1.5 |
| 年間コスト | ~$18 |

## Implementation

- `evaluation/judge.py` — Gemini Flash LangChain wrapper
- `evaluation/run_ragas.py` — dataset loading + RAGAS evaluate + regression check
- `evaluation/datasets/qa_v1.json` — 25 件 QA (定義 5 / 比較 5 / Why 5 / How 5 / エッジ 5)
- `.github/workflows/ragas.yml` — nightly + PR トリガー + PR コメント

## Future

- spec_036 (v0.8): regression で exit 1 に変更 + PR コメントに block 理由追記
- spec_037 (v0.8): qa_v2.json (50 件、多言語対応)
- spec_038 (v0.8): A/B フラグで parent_doc.enabled true/false 並列比較
- spec_039 (v0.8): GitHub Pages でスコア推移グラフを公開

## Update (2026-05-14, spec_038)

### Regression blocking

`--block-on-regression` フラグを追加 (default off)。5% drop で exit 1。
v0.8 リリース時点では **CI に組み込まない** — 1 週間 nightly 観察後、誤検出率に基づいて enable する。

### A/B 評価

`run_abtest.py` を新設。paired t-test (scipy) で有意性判定。
`time_decay.enabled` の効果検証から開始。半年運用後の所感を ADR-021 に reflect。

### コスト追記

A/B 1 回で **judge call 200 回** (25 × 4 metrics × 2 config) → ~$0.10/run。月 1 回想定で +$0.10/月。

## Update (2026-05-14, spec_042) — EVAL_OVERRIDE_FLAG wiring

spec_038 では `run_abtest.py` が `os.environ["EVAL_OVERRIDE_FLAG"]` を set していたが、`load_app_config()` がこの環境変数を読み取らない実装漏れがあり、A/B 両 run が同一 config で走っていた (spec_041 review で HIGH 指摘)。

### 修正

`load_app_config()` を 2 段構成にリファクタ:

1. yaml → typed `AppConfig` (`_build_app_config`)
2. `EVAL_OVERRIDE_FLAG` 環境変数があれば dotted-key=value で in-memory override (`_apply_override_flags`)

複数 key は `;` 区切り。

```
EVAL_OVERRIDE_FLAG="retrieval.time_decay.enabled=true;chat.enabled=false"
```

### 型強制 (_coerce_value)

| 入力 | 型 |
|---|---|
| `"true"` / `"false"` (case-insensitive) | `bool` |
| 整数表現 | `int` |
| 浮動小数表現 | `float` |
| それ以外 | `str` |

### Unknown key

`AppConfig` に存在しないキーは `WARNING` ログ + skip。本番稼働中に古い env var が残っていても API が落ちないようにする (silent fail を採用)。

### 影響

`evaluation/run_abtest.py` のコード側に変更なし。同じ環境変数を set している既存呼び出しが **意味的に initial 動作するようになる**。
