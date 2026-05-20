"""Generate weekly markdown reports from feedback records (spec_047).

Reads from any ``FeedbackStore`` (currently only ``SqliteFeedbackStore``)
and produces a small Markdown summary suitable for pasting into Slack /
saving under ``evaluation/feedback_reports/YYYY-WW.md``.

The aggregations are deliberately simple — frequent queries, doc-level
net 👍/👎, etc. Anything more elaborate (clustering, automatic weight
adjustment) is parked for v0.10.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path


def generate_report(store, *, days: int = 7) -> str:  # type: ignore[no-untyped-def]
    """Return a Markdown report of feedback activity over the last ``days``.

    Empty windows return a short placeholder rather than an error, so
    callers (the API endpoint, the Makefile target) can always render
    something.
    """
    records = store.list_recent(days=days)
    if not records:
        return (
            f"# Feedback report ({days}d)\n\n"
            f"No feedback recorded in the last {days} days.\n"
        )

    pos = [r for r in records if r.rating > 0]
    neg = [r for r in records if r.rating < 0]
    neutral = [r for r in records if r.rating == 0]

    # doc_id ごとの net score
    by_doc: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [pos, neg]
    for r in records:
        if not r.doc_id:
            continue
        if r.rating > 0:
            by_doc[r.doc_id][0] += 1
        elif r.rating < 0:
            by_doc[r.doc_id][1] += 1

    # Sort by net negative (most 👎 over 👍) for the "unpopular" section,
    # then by the opposite for "popular". A doc that ties pos==neg shows
    # up in neither top-5 list, which is what we want — those are the
    # docs to ignore in a weekly review.
    unpopular = sorted(
        by_doc.items(), key=lambda kv: kv[1][1] - kv[1][0], reverse=True
    )[:5]
    popular = sorted(
        by_doc.items(), key=lambda kv: kv[1][0] - kv[1][1], reverse=True
    )[:5]

    # 検索されたがフィードバック付かなかった query (= miss?)
    queries: dict[str, int] = defaultdict(int)
    for r in records:
        if r.query:
            queries[r.query] += 1
    top_queries = sorted(queries.items(), key=lambda kv: kv[1], reverse=True)[:10]

    lines: list[str] = [
        f"# Feedback report "
        f"({days}d, generated {datetime.now(UTC).strftime('%Y-%m-%d')})",
        "",
        f"- Total: **{len(records)}** records",
        f"  - 👍 helpful: {len(pos)}",
        f"  - 👎 not helpful: {len(neg)}",
    ]
    if neutral:
        lines.append(f"  - ⚪ neutral: {len(neutral)}")
    lines.extend(["", "## Top queries"])
    if not top_queries:
        lines.append("- (no query strings recorded)")
    for q, c in top_queries:
        lines.append(f"- {q!r}: {c} interactions")

    lines.extend(["", "## Unpopular docs (net 👎)"])
    if not unpopular:
        lines.append("- (no doc-level feedback recorded)")
    for doc_id, (p, n) in unpopular:
        net = n - p
        if net <= 0:
            continue  # nothing actually unpopular in this window
        lines.append(f"- `{doc_id}`: +{p} / -{n} (net -{net})")

    lines.extend(["", "## Popular docs (net 👍)"])
    if not popular:
        lines.append("- (no doc-level feedback recorded)")
    for doc_id, (p, n) in popular:
        net = p - n
        if net <= 0:
            continue
        lines.append(f"- `{doc_id}`: +{p} / -{n} (net +{net})")

    return "\n".join(lines) + "\n"


def save_report_to_file(
    store,  # type: ignore[no-untyped-def]
    *,
    days: int = 7,
    output_dir: str = "evaluation/feedback_reports",
) -> str:
    """Render a report and persist it under ``{output_dir}/YYYY-WW.md``.

    The filename uses ISO week numbers so re-running on the same day
    overwrites the same file — which is the intended UX for "current
    week's snapshot."
    """
    md = generate_report(store, days=days)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    year, week, _ = datetime.now(UTC).isocalendar()
    fname = f"{year}-W{week:02d}.md"
    path = out_dir / fname
    path.write_text(md, encoding="utf-8")
    return str(path)
