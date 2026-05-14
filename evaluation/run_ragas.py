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
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

from evaluation.judge import get_judge_embeddings, get_judge_llm

METRICS = [faithfulness, answer_relevancy, context_precision, context_recall]


def _build_pipeline():
    """Instantiate SearchEngine + RAGPipeline from project config."""
    from backend.src.bm25_index import BM25Index
    from backend.src.config import load_axes_config, settings
    from backend.src.embedder import Embedder
    from backend.src.normalizer import Normalizer
    from backend.src.rag import RAGPipeline
    from backend.src.search import SearchEngine
    from backend.src.vector_store import VectorStore

    store = VectorStore(path=settings.chroma_db_path)
    embedder = Embedder()
    normalizer = Normalizer.from_config(load_axes_config())
    try:
        bm25 = BM25Index.load(settings.chroma_db_path / "bm25_index.pkl")
    except Exception:
        bm25 = None
    engine = SearchEngine(store, embedder, normalizer, bm25_index=bm25)
    pipeline = RAGPipeline(engine)
    return engine, pipeline


def run_pipeline(
    engine, pipeline, question: str, axes: dict[str, Any] | None
) -> tuple[str, list[str]]:
    """Run search + RAG and return (answer_text, retrieved_contexts)."""
    results = engine.search(question, filters=axes, top_k=5)
    from backend.src.rag import _dummy_answer

    if pipeline.is_dummy:
        ans = _dummy_answer(question, results)
    else:
        ans = pipeline.answer(question, filters=axes, top_k=5)
    contexts = [r.body_snippet for r in results]
    return ans.text, contexts


def build_dataset(qa_path: Path, engine, pipeline) -> Dataset:
    raw = json.loads(qa_path.read_text(encoding="utf-8"))
    rows = []
    for item in raw["items"]:
        ans, ctx = run_pipeline(engine, pipeline, item["question"], item.get("axes"))
        rows.append(
            {
                "question": item["question"],
                "answer": ans,
                "contexts": ctx,
                "ground_truth": item["ground_truth"],
            }
        )
    return Dataset.from_list(rows)


def main() -> int:
    p = argparse.ArgumentParser(description="Run RAGAS evaluation.")
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument(
        "--baseline", type=Path, default=Path("evaluation/baseline.json")
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--update-baseline", action="store_true")
    p.add_argument(
        "--regression-threshold",
        type=float,
        default=0.05,
        help="Warn if any metric drops by more than this fraction vs baseline.",
    )
    args = p.parse_args()

    engine, pipeline = _build_pipeline()
    ds = build_dataset(args.dataset, engine, pipeline)

    result = evaluate(
        ds,
        metrics=METRICS,
        llm=get_judge_llm(),
        embeddings=get_judge_embeddings(),
    )

    scores = {m.name: float(result[m.name]) for m in METRICS}
    record: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
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
        print(f"\nBaseline updated: {args.baseline}")

    # v0.7: WARN only — exit 0 regardless of regressions. v0.8 will block.
    return 0


def _check_regression(
    scores: dict[str, float], baseline_path: Path, threshold: float
) -> list[tuple[str, float, float]]:
    if not baseline_path.exists():
        return []
    baseline = json.loads(baseline_path.read_text())["scores"]
    out = []
    for k, v in scores.items():
        b = baseline.get(k)
        if b is None or b == 0.0:
            continue
        if (b - v) / b > threshold:
            out.append((k, b, v))
    return out


def _print_summary(
    scores: dict[str, float], regressions: list[tuple[str, float, float]]
) -> None:
    print("\n## RAGAS Scores")
    for k, v in scores.items():
        print(f"  {k:25s}  {v:.4f}")
    if regressions:
        print("\n## Regressions vs baseline")
        for k, b, v in regressions:
            print(f"  WARN {k}: {b:.4f} -> {v:.4f} ({(v - b) / b * 100:+.1f}%)")
    else:
        print("\nNo regressions detected.")


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"])
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
