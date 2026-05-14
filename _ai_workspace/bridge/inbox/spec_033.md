# spec_033: RAGAS CI/CD (LLM-as-a-Judge 自動評価)

- **Author**: Cowork (中島)
- **Created**: 2026-05-14
- **Target**: Claude Code (`dev-d`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Bundles**: v0.7 コア 3/3。spec_031 (Parent Doc) / spec_032 (Conversational) と独立に開発可能。ただし **両方 merge 後** に baseline を更新するのが理想 (評価対象が増えるため)

## 1. 目的

v0.6 まで「検索精度が上がった」「BM25 ハイブリッドで改善した」と主張してきたが、**数値根拠が無い**。手動の sample query 5-10 件で「良くなった気がする」と判断してきた段階。

ポートフォリオ / ES 観点で「**LLM as a Judge による自動評価を CI に組み込み、回帰を自動検出**」というのは大きな差別化要素。RAGAS のメトリクスを CI に組み込み、PR 単位で品質変動を可視化する。

```
[現状 v0.6.0]
- 評価データセット: なし
- メトリクス: なし
- CI: ruff + pytest のみ。検索品質の回帰は気付けない

[変更後 v0.7 (spec_033)]
- evaluation/ ディレクトリ新設
- 25 件 QA データセット (examples/knowledge/ をカバー)
- RAGAS 4 メトリクス: faithfulness / answer_relevancy / context_precision / context_recall
- judge model: Gemini 1.5 Flash (LLM Judge コスト ~$0.05/run)
- baseline.json で前回スコアを保存、PR で diff 表示
- GitHub Actions: nightly + 関連ファイル変更 PR で実行
- 閾値違反は v0.7 は WARN only (block しない)、v0.8 で block 化
- README に RAGAS バッジ (latest score)
```

## 2. 制約

### 触ってよいファイル

- `evaluation/` ディレクトリ全体 — **新規**
  - `evaluation/__init__.py`
  - `evaluation/datasets/qa_v1.json` — 25 QA pairs
  - `evaluation/run_ragas.py` — メイン runner
  - `evaluation/baseline.json` — 直近スコア (CI が更新する)
  - `evaluation/judge.py` — Gemini Flash wrapper
  - `evaluation/requirements.txt` — ragas + datasets 等
  - `evaluation/README.md` — 使い方
- `.github/workflows/ragas.yml` — **新規** CI workflow
- `Makefile` — `eval` ターゲット追加 (なければ作る)
- `pyproject.toml` — `[project.optional-dependencies]` の `eval` セクション追加 (任意)
- `docs/adr/ADR-019-ragas-evaluation.md` — **新規**
- `docs/evaluation.md` — **新規** (データセット仕様、judge 選定理由、メトリクス解説)
- `README.md` — RAGAS バッジ + Evaluation セクション追加
- `CHANGELOG.md` — Day 33 追記

### 触ってはいけないもの

- `backend/src/` — search/rag のロジックを変えない。RAGAS は evaluation 側からこれらを呼ぶだけ
- `mcp_server/` / `frontend/` / `streamlit_app.py`
- 既存 `.github/workflows/{ci.yml, docker-build.yml}` — 触らない (別 workflow ファイルとして追加)
- `_ai_workspace/`

### コーディングルール

- ragas は **本体実行に不要** なオプショナル依存。`pip install -e ".[eval]"` で入る
- judge LLM の API キーは GitHub Secret `GEMINI_API_KEY` (既存) を再利用
- データセットは markdown + 期待出典 ID で書く。CC が自分で起案して OK (本 spec の Open questions に提示推奨)
- 既存 pytest workflow と切り離す (RAGAS は重い & flaky なので)

### デプロイ

- 本 spec は実装のみ。tag は v0.7.0 で一括

## 3. やってほしいこと

### 3-1. データセット (`evaluation/datasets/qa_v1.json`)

```json
{
  "version": 1,
  "created": "2026-05-14",
  "description": "axis-knowledge-rag v0.7 baseline QA set. Covers examples/knowledge/*.",
  "items": [
    {
      "id": "qa_001",
      "question": "RAG とは何か、3 行で説明してください",
      "ground_truth": "RAG (Retrieval-Augmented Generation) は、外部知識を検索して生成 AI のプロンプトに含めることで、ハルシネーションを減らし最新情報を反映できる手法。検索 → 文脈付与 → 生成の 3 段階で構成される。",
      "expected_contexts": ["01-rag-patterns.md"],
      "axes": null
    },
    {
      "id": "qa_002",
      "question": "ベクトル検索と全文検索 (BM25) の違いは?",
      "ground_truth": "ベクトル検索は意味の近さで類似度を測り、BM25 は語彙の出現頻度で類似度を測る。ベクトルは同義語/言い換えに強く、BM25 は固有名詞や明示的キーワードに強い。実用では両者をハイブリッドして補完する。",
      "expected_contexts": ["02-vector-search.md", "01-rag-patterns.md"],
      "axes": null
    }
    // ... 計 25 件
  ]
}
```

#### 25 件の構成案 (CC が起案して構わない、参考):

- カバレッジ: `examples/knowledge/01-rag-patterns.md` ~ `05-prompt-engineering.md` を **各 5 件**
- 種別:
  - 5 件 — 定義系 (「~ とは?」)
  - 5 件 — 比較系 (「A と B の違いは?」)
  - 5 件 — Why 系 (「なぜ ~?」)
  - 5 件 — How 系 (「~ を実装するには?」)
  - 5 件 — エッジケース (axes フィルタ込み、または該当文書なし)

ground_truth は 100-300 字。`expected_contexts` は relevant な doc_id (relative path)。

### 3-2. Judge wrapper (`evaluation/judge.py`)

```python
"""Gemini 1.5 Flash adapter for ragas LLM judge."""

from __future__ import annotations
import os
import google.generativeai as genai
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI


def get_judge_llm() -> BaseChatModel:
    """Return ragas-compatible Gemini Flash LLM."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        temperature=0.0,
        google_api_key=api_key,
    )


def get_judge_embeddings():
    """Embeddings for ragas semantic similarity metrics."""
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    return GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004",
        google_api_key=os.environ["GEMINI_API_KEY"],
    )
```

### 3-3. Runner (`evaluation/run_ragas.py`)

```python
"""Run ragas evaluation over qa_v1.json.

Usage:
    python -m evaluation.run_ragas \\
        --dataset evaluation/datasets/qa_v1.json \\
        --baseline evaluation/baseline.json \\
        --output evaluation/runs/$(date +%Y%m%d-%H%M).json \\
        --update-baseline
"""

from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)

from backend.src import rag, search
from evaluation.judge import get_judge_llm, get_judge_embeddings


METRICS = [faithfulness, answer_relevancy, context_precision, context_recall]


def run_pipeline(question: str, axes: dict | None) -> tuple[str, list[str]]:
    """Run our actual search + RAG and return (answer, retrieved_contexts)."""
    hits = search.search(question, axes=axes, k=5)
    answer, _sources = rag.answer_from_hits(question, hits)
    contexts = [h.text for h in hits]
    return answer, contexts


def build_dataset(qa_path: Path) -> Dataset:
    raw = json.loads(qa_path.read_text(encoding="utf-8"))
    rows = []
    for item in raw["items"]:
        ans, ctx = run_pipeline(item["question"], item.get("axes"))
        rows.append({
            "question": item["question"],
            "answer": ans,
            "contexts": ctx,
            "ground_truth": item["ground_truth"],
        })
    return Dataset.from_list(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--baseline", type=Path, default=Path("evaluation/baseline.json"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--update-baseline", action="store_true")
    p.add_argument("--regression-threshold", type=float, default=0.05,
                   help="Warn if any metric drops by more than this fraction")
    args = p.parse_args()

    ds = build_dataset(args.dataset)
    result = evaluate(
        ds, metrics=METRICS,
        llm=get_judge_llm(),
        embeddings=get_judge_embeddings(),
    )

    scores = {m.name: float(result[m.name]) for m in METRICS}
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "dataset": str(args.dataset),
        "scores": scores,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, ensure_ascii=False))

    regressions = _check_regression(scores, args.baseline, args.regression_threshold)
    _print_summary(scores, regressions)

    if args.update_baseline:
        args.baseline.write_text(json.dumps(record, indent=2, ensure_ascii=False))

    # v0.7: WARN only (exit 0)。v0.8 で block 化検討。
    return 0


def _check_regression(scores, baseline_path, threshold):
    if not baseline_path.exists():
        return []
    baseline = json.loads(baseline_path.read_text())["scores"]
    out = []
    for k, v in scores.items():
        b = baseline.get(k)
        if b is None:
            continue
        if (b - v) / b > threshold:
            out.append((k, b, v))
    return out


def _print_summary(scores, regressions):
    print("\n## RAGAS Scores")
    for k, v in scores.items():
        print(f"  {k:25s}  {v:.4f}")
    if regressions:
        print("\n## Regressions vs baseline")
        for k, b, v in regressions:
            print(f"  WARN {k}: {b:.4f} -> {v:.4f} ({(v - b) / b * 100:+.1f}%)")


def _git_sha():
    import subprocess
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()


if __name__ == "__main__":
    raise SystemExit(main())
```

### 3-4. baseline.json (初期版)

最初の実行で生成される。テンプレ:

```json
{
  "timestamp": "2026-05-14T00:00:00Z",
  "git_sha": "<bootstrap>",
  "dataset": "evaluation/datasets/qa_v1.json",
  "scores": {
    "faithfulness": 0.0,
    "answer_relevancy": 0.0,
    "context_precision": 0.0,
    "context_recall": 0.0
  }
}
```

CC は初回実行後に **`--update-baseline` で実スコアに上書き** してコミットすること。

### 3-5. CI workflow (`.github/workflows/ragas.yml`)

```yaml
name: RAGAS Evaluation

on:
  schedule:
    - cron: "0 18 * * *"  # 03:00 JST 毎日
  pull_request:
    paths:
      - "backend/src/search.py"
      - "backend/src/rag.py"
      - "backend/src/chunker.py"
      - "backend/src/bm25*.py"
      - "evaluation/**"
      - "config.yml"
  workflow_dispatch:

jobs:
  ragas:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[eval]"

      - name: Build index
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python scripts/build_index.py --rebuild

      - name: Run RAGAS
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          mkdir -p evaluation/runs
          python -m evaluation.run_ragas \
            --dataset evaluation/datasets/qa_v1.json \
            --baseline evaluation/baseline.json \
            --output evaluation/runs/ci-${{ github.sha }}.json
        continue-on-error: true  # v0.7: WARN only

      - name: Comment scores on PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const out = JSON.parse(fs.readFileSync(`evaluation/runs/ci-${{ github.sha }}.json`));
            const base = JSON.parse(fs.readFileSync('evaluation/baseline.json'));
            const lines = ['## RAGAS scores', '', '| metric | this PR | baseline | Δ |', '|---|---|---|---|'];
            for (const k of Object.keys(out.scores)) {
              const v = out.scores[k].toFixed(4);
              const b = (base.scores[k] || 0).toFixed(4);
              const d = (out.scores[k] - (base.scores[k] || 0)).toFixed(4);
              lines.push(`| ${k} | ${v} | ${b} | ${d} |`);
            }
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: lines.join('\n'),
            });

      - name: Upload run artifact
        uses: actions/upload-artifact@v4
        with:
          name: ragas-run-${{ github.sha }}
          path: evaluation/runs/

      - name: Update baseline (nightly only)
        if: github.event_name == 'schedule'
        run: |
          python -m evaluation.run_ragas \
            --dataset evaluation/datasets/qa_v1.json \
            --output evaluation/runs/nightly-${{ github.sha }}.json \
            --update-baseline
          if [[ -n "$(git status --porcelain evaluation/baseline.json)" ]]; then
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add evaluation/baseline.json
            git commit -m "chore(ragas): nightly baseline update"
            git push
          fi
```

### 3-6. Makefile

```makefile
.PHONY: eval eval-update-baseline

eval:
	python -m evaluation.run_ragas \
		--dataset evaluation/datasets/qa_v1.json \
		--baseline evaluation/baseline.json \
		--output evaluation/runs/local-$$(date +%Y%m%d-%H%M).json

eval-update-baseline:
	python -m evaluation.run_ragas \
		--dataset evaluation/datasets/qa_v1.json \
		--baseline evaluation/baseline.json \
		--output evaluation/runs/local-$$(date +%Y%m%d-%H%M).json \
		--update-baseline
```

### 3-7. pyproject.toml

```toml
[project.optional-dependencies]
eval = [
    "ragas>=0.2.0",
    "datasets>=2.20",
    "langchain-google-genai>=2.0",
    "langchain-core>=0.3",
]
```

### 3-8. README に追加

#### バッジ

```markdown
[![RAGAS](https://img.shields.io/badge/RAGAS-faithfulness%200.87%20%7C%20relevancy%200.85-brightgreen.svg)](evaluation/baseline.json)
```

(初回実行後にスコアで置換。CC は手動でバッジ文字列を更新)

#### Evaluation セクション

```markdown
## Evaluation

本リポジトリは [RAGAS](https://docs.ragas.io/) を使って **検索 + 生成品質を自動評価** しています。

| メトリクス | スコア | 説明 |
|---|---|---|
| faithfulness | 0.87 | 生成回答が retrieved context に忠実か |
| answer_relevancy | 0.85 | 質問に対する回答の妥当性 |
| context_precision | 0.79 | 取得した context のうち真に必要な割合 |
| context_recall | 0.82 | 正答を裏付ける context を取得できた割合 |

ローカル実行:

\`\`\`bash
pip install -e ".[eval]"
make eval
\`\`\`

CI でも毎日 03:00 JST に実行、PR で関連ファイルが変更されると自動でコメント (`.github/workflows/ragas.yml`)。
```

### 3-9. ADR-019

`docs/adr/ADR-019-ragas-evaluation.md`:

- Context: 検索品質の回帰検出が手動依存
- Decision: RAGAS + Gemini 1.5 Flash judge を CI に組み込み
- Alternatives:
  - (a) OpenAI GPT-4 judge → 却下 (コスト 10x)
  - (b) BLEU / ROUGE → 却下 (生成 RAG 品質には不適切)
  - (c) 自前で LLM Judge プロンプト → 却下 (再現性と peer comparison の観点で RAGAS 採用)
- Consequences:
  - judge コスト ~$0.05/run × 30 runs/月 = $1.5/月
  - GEMINI_API_KEY を CI Secret に設定済み前提
  - v0.7 では WARN only。誤検出を見ながら閾値を ADR-019 で update

### 3-10. 動作確認

```bash
cd ~/projects/axis-knowledge-rag
git checkout -b feat/spec_033-ragas-ci

# Install eval extras
pip install -e ".[eval]"

# Lint
ruff check evaluation/

# Smoke test: 25 件中 3 件だけサンプル抽出
jq '.items |= .[0:3]' evaluation/datasets/qa_v1.json > /tmp/qa_smoke.json
python -m evaluation.run_ragas \
  --dataset /tmp/qa_smoke.json \
  --baseline evaluation/baseline.json \
  --output /tmp/smoke.json
cat /tmp/smoke.json | jq .scores

# Full run (~5-10 min, judge call ~100 回)
make eval
cat evaluation/runs/local-*.json | tail -1 | jq .scores

# Update baseline
make eval-update-baseline
git diff evaluation/baseline.json

# CI workflow syntax check
actionlint .github/workflows/ragas.yml 2>&1 || true  # actionlint があれば
```

### 3-11. コミット粒度

1. `feat(eval): scaffold evaluation/ directory + 25-item qa_v1.json`
2. `feat(eval): Gemini Flash judge wrapper + run_ragas.py main`
3. `feat(eval): baseline.json + regression detection (WARN only)`
4. `chore: add ragas/datasets/langchain-google-genai as optional [eval] extras`
5. `feat(make): eval and eval-update-baseline targets`
6. `feat(ci): RAGAS workflow with nightly + PR triggers + comment-on-PR`
7. `docs: ADR-019 + docs/evaluation.md + README Evaluation section`
8. `chore: CHANGELOG Day 33`
9. `chore(eval): initial baseline scores from first full run`

`git push -u origin feat/spec_033-ragas-ci`

### 3-12. result_033.md に書くこと

- 25 件 QA dataset の構成 (種別ごとの内訳)
- 初回 RAGAS 実行の生スコア (4 メトリクス)
- judge call 数 + 実コスト (Gemini Flash 課金ダッシュボード参照)
- CI workflow が手動 dispatch で緑になるか確認 (`gh workflow run ragas.yml`)
- PR コメント機能のスクショ手順 (テスト PR を 1 本立てて動作確認)

## 4. 成功条件

- [ ] `evaluation/datasets/qa_v1.json` に 25 件、各 ground_truth + expected_contexts 完備
- [ ] `python -m evaluation.run_ragas` がローカルで完走 (~10 min 以内)
- [ ] `evaluation/baseline.json` に初回実スコアが入っている
- [ ] `.github/workflows/ragas.yml` が actions/checkout から最後まで通る (手動 dispatch で確認)
- [ ] README に Evaluation セクション + RAGAS バッジ
- [ ] ADR-019 / docs/evaluation.md
- [ ] 既存 169 tests に影響なし (eval は別 path)
- [ ] git push 完了

## 5. 出力先

`~/projects/axis-knowledge-rag/_ai_workspace/bridge/outbox/result_033.md`

## 6. 質問があるとき

- **judge model 選定**: gemini-1.5-flash で 25 件 × 4 metrics = 100 call/run。flash-8b に下げた方が安いが品質低下リスクあり。CC 判断で OK、ADR-019 に根拠書く
- **embeddings**: ragas は context_precision/recall に embeddings を使う。`text-embedding-004` (本体と同じ) で OK。コスト懸念があれば `text-embedding-001` に降格
- **regression threshold**: 5% に設定したが、CI で毎日 stochastic に揺らぐので 5-10% の範囲で調整 (CC が初週運用しながら決める)
- **dataset 25 件は妥当か**: 50 件まで増やすとカバレッジ上がるが judge コスト 2x。v0.7 では 25 件で baseline 確立、v0.8 で 50 件に拡張する方針

迷ったら Open questions に書いて `status: blocked` で終了。

## 7. 補足

### 設計の意図

- 「LLM 駆動の自動評価」は採用面でインパクト大 (LangSmith / Phoenix と肩を並べる体裁)
- ragas は v0.2 以降 ChromaDB / 自前 retriever でも動かしやすい
- WARN only スタートで誤検出を見ながら閾値調整、これが現実的

### 将来の拡張余地

- spec_036 候補 (v0.8): block on regression + comment-bot で人間レビュー誘導
- spec_037 候補 (v0.8): qa_v2.json (50 件、多言語対応)
- spec_038 候補 (v0.8): A/B フラグでメトリクス分岐評価 (parent_doc.enabled true vs false で並列比較)
- spec_039 候補 (v0.8): 公開リーダーボード (GitHub Pages) で nightly score 推移可視化
