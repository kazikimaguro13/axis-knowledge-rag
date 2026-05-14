"""Statistical analysis for RAGAS scores."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TTestResult:
    metric: str
    mean_a: float
    mean_b: float
    diff: float  # mean_b - mean_a
    t_statistic: float
    p_value: float
    significant: bool  # p < 0.05
    direction: str  # "B>A" | "A>B" | "tie"


def paired_t_test(
    scores_a: list[float], scores_b: list[float], *, alpha: float = 0.05
) -> TTestResult | None:
    """Run paired t-test on two RAGAS score arrays for the same metric.

    Returns None if scipy not available (graceful degradation).
    """
    if len(scores_a) != len(scores_b) or len(scores_a) < 2:
        raise ValueError(
            f"need same-length arrays >= 2, got {len(scores_a)} vs {len(scores_b)}"
        )
    try:
        from scipy import stats
    except ImportError:
        return None
    result = stats.ttest_rel(scores_b, scores_a)
    diff = sum(scores_b) / len(scores_b) - sum(scores_a) / len(scores_a)
    direction = "tie"
    if result.pvalue < alpha:
        direction = "B>A" if diff > 0 else "A>B"
    return TTestResult(
        metric="",  # caller fills
        mean_a=sum(scores_a) / len(scores_a),
        mean_b=sum(scores_b) / len(scores_b),
        diff=diff,
        t_statistic=float(result.statistic),
        p_value=float(result.pvalue),
        significant=bool(result.pvalue < alpha),
        direction=direction,
    )
