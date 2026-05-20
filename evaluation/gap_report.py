"""Generate weekly markdown reports from knowledge-gap records (spec_048).

Reads from any ``GapStore`` (currently only ``SqliteGapStore``) and
produces a short Markdown summary suitable for pasting into Slack /
saving under ``evaluation/gap_reports/YYYY-WW.md``. The aggregations
are deliberately simple — frequent unsatisfied queries grouped by
reason. Anything more elaborate (clustering, LLM-suggested topic
ingestion) is parked for v0.10 (see ADR-029).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path


def generate_report(store, *, days: int = 7) -> str:  # type: ignore[no-untyped-def]
    """Return a Markdown report of gap events over the last ``days``.

    Empty windows return a short placeholder rather than an error, so
    callers (the API endpoint, the Makefile target) can always render
    something.
    """
    records = store.list_recent(days=days)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if not records:
        return (
            f"# Knowledge gap report ({days}d, generated {today})\n\n"
            f"No knowledge gaps detected in the last {days} days.\n"
        )

    by_query: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "reasons": defaultdict(int), "scores": []}
    )
    for r in records:
        entry = by_query[r.query]
        entry["count"] += 1
        entry["reasons"][r.reason] += 1
        if r.top_score is not None:
            entry["scores"].append(r.top_score)

    # Top 10 unsatisfied queries by event count (descending). Stable tie-
    # break on the query string keeps the report deterministic across
    # identical re-runs.
    top = sorted(
        by_query.items(),
        key=lambda kv: (-kv[1]["count"], kv[0]),
    )[:10]

    # Global reason counts — useful for "is the dominant signal
    # no_results or llm_no_info?" at a glance.
    reason_totals: dict[str, int] = defaultdict(int)
    for r in records:
        reason_totals[r.reason] += 1

    lines: list[str] = [
        f"# Knowledge gap report ({days}d, generated {today})",
        "",
        f"- **{len(records)}** gap events total, "
        f"**{len(by_query)}** distinct queries",
    ]
    for reason in ("no_results", "low_score", "llm_no_info"):
        if reason_totals.get(reason):
            lines.append(f"  - `{reason}`: {reason_totals[reason]}")
    lines.extend(["", "## Top unsatisfied queries", ""])

    for q, info in top:
        scores = info["scores"]
        avg_score = sum(scores) / len(scores) if scores else None
        reasons_str = ", ".join(
            f"{k}:{v}" for k, v in sorted(info["reasons"].items())
        )
        score_str = (
            f"avg top_score={avg_score:.3f}"
            if avg_score is not None
            else "no scores recorded"
        )
        lines.append(
            f"- **{q}**: {info['count']}x [{reasons_str}] ({score_str})"
        )

    lines.extend(
        [
            "",
            "## 推奨アクション",
            "",
            "- 上記の query に該当する topic のメモを "
            "`examples/knowledge/` に追加することを推奨。",
            "- ブラウザ拡張 (spec_046) から関連記事を `/api/ingest` で "
            "取り込む or Markdown を手書きで追加 → "
            "`scripts/build_index.py --rebuild` で反映。",
            "- 自動 ingest 案 (LLM が query から frontmatter 候補を生成) "
            "は v0.10 で検討中 (ADR-029 §Alternatives 参照)。",
        ]
    )
    return "\n".join(lines) + "\n"


def save_report_to_file(
    store,  # type: ignore[no-untyped-def]
    *,
    days: int = 7,
    output_dir: str = "evaluation/gap_reports",
) -> str:
    """Render a report and persist it under ``{output_dir}/YYYY-WW.md``.

    The filename uses ISO week numbers so re-running on the same day
    overwrites the same file — matching the spec_047 ``feedback-report``
    UX exactly.
    """
    md = generate_report(store, days=days)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    year, week, _ = datetime.now(UTC).isocalendar()
    fname = f"{year}-W{week:02d}.md"
    path = out_dir / fname
    path.write_text(md, encoding="utf-8")
    return str(path)
