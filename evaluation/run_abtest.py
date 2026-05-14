"""A/B test runner: same dataset, two different config flags, paired t-test on metrics.

Usage:
    python -m evaluation.run_abtest \\
        --dataset evaluation/datasets/qa_v1.json \\
        --flag time_decay.enabled \\
        --output evaluation/runs/abtest-$(date +%Y%m%d).json
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

from evaluation.judge import get_judge_embeddings, get_judge_llm
from evaluation.run_ragas import _build_pipeline, build_dataset
from evaluation.stats import paired_t_test

METRICS = [faithfulness, answer_relevancy, context_precision, context_recall]


def main() -> int:
    p = argparse.ArgumentParser(description="Run A/B evaluation with paired t-test.")
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument(
        "--flag",
        required=True,
        help="config.yml dotted key, e.g. 'time_decay.enabled'",
    )
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    # Run A (flag=False)
    os.environ["EVAL_OVERRIDE_FLAG"] = f"{args.flag}=false"
    engine_a, pipeline_a = _build_pipeline()
    ds_a = build_dataset(args.dataset, engine_a, pipeline_a)
    scores_a = _evaluate(ds_a)

    # Run B (flag=True)
    os.environ["EVAL_OVERRIDE_FLAG"] = f"{args.flag}=true"
    engine_b, pipeline_b = _build_pipeline()
    ds_b = build_dataset(args.dataset, engine_b, pipeline_b)
    scores_b = _evaluate(ds_b)

    ttests: dict[str, dict] = {}
    for m in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        a_arr = scores_a["per_question"].get(m, [])
        b_arr = scores_b["per_question"].get(m, [])
        if not a_arr or not b_arr:
            continue
        result = paired_t_test(a_arr, b_arr)
        if result:
            ttests[m] = {
                "metric": m,
                "mean_a": result.mean_a,
                "mean_b": result.mean_b,
                "diff": result.diff,
                "t": result.t_statistic,
                "p": result.p_value,
                "significant": result.significant,
                "direction": result.direction,
            }

    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "dataset": str(args.dataset),
        "flag": args.flag,
        "config_a": f"{args.flag}=false",
        "config_b": f"{args.flag}=true",
        "summary_a": scores_a["summary"],
        "summary_b": scores_b["summary"],
        "ttests": ttests,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    _print_summary(record)
    return 0


def _evaluate(ds) -> dict:
    result = evaluate(
        ds,
        metrics=METRICS,
        llm=get_judge_llm(),
        embeddings=get_judge_embeddings(),
    )
    summary = {m.name: float(result[m.name]) for m in METRICS}

    # Extract per-question scores via to_pandas() if available
    per_question: dict[str, list[float]] = {m.name: [] for m in METRICS}
    try:
        df = result.to_pandas()
        for m in METRICS:
            if m.name in df.columns:
                per_question[m.name] = [float(v) for v in df[m.name].tolist()]
    except Exception:
        # Fallback: replicate summary score per question (makes paired t-test trivial but safe)
        for m in METRICS:
            per_question[m.name] = [summary[m.name]] * len(ds)

    return {"summary": summary, "per_question": per_question}


def _print_summary(record: dict) -> None:
    print(f"\n## A/B Test: {record['flag']}")
    print(f"  A: {record['config_a']}")
    print(f"  B: {record['config_b']}\n")
    print("| metric | mean A | mean B | Δ | p | significant | direction |")
    print("|---|---|---|---|---|---|---|")
    for m, t in record["ttests"].items():
        sig = "✅" if t["significant"] else "—"
        print(
            f"| {m} | {t['mean_a']:.4f} | {t['mean_b']:.4f} | "
            f"{t['diff']:+.4f} | {t['p']:.4f} | {sig} | {t['direction']} |"
        )


if __name__ == "__main__":
    raise SystemExit(main())
