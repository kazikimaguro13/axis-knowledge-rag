"""Markdown / JSON formatters shared across tools."""

import json
from typing import Any

from backend.src.integrity import IntegrityReport
from backend.src.search import SearchResult


def format_search_results_md(query: str | None, filters: dict, results: list[SearchResult]) -> str:
    lines = []
    title = f"Search results for: `{query}`" if query else "Axis-only filter results"
    lines.append(f"# {title}")
    if filters:
        lines.append(f"\n**Filters**: {filters}\n")
    lines.append(f"\n**{len(results)}** result(s)\n")
    for r in results:
        lines.append(f"## [{r.score:.3f}] `{r.id}` — {r.title}")
        lines.append(f"- axes: {r.axes}")
        if r.refs:
            lines.append(f"- refs: {r.refs}")
        lines.append(f"\n{r.body_snippet}\n")
    return "\n".join(lines)


def format_search_results_json(query: str | None, filters: dict, results: list[SearchResult]) -> str:
    payload = {
        "query": query,
        "filters": filters,
        "count": len(results),
        "results": [
            {
                "id": r.id,
                "title": r.title,
                "score": r.score,
                "axes": r.axes,
                "body_snippet": r.body_snippet,
                "path": r.path,
                "refs": r.refs,
            }
            for r in results
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def format_integrity_md(report: IntegrityReport) -> str:
    lines = ["# Integrity Report", ""]
    lines.append(f"- Total documents: {report.total_docs}")
    lines.append(f"- Total refs:      {report.total_refs}")
    lines.append("")
    if report.broken_refs:
        lines.append(f"## Broken refs ({len(report.broken_refs)})")
        for b in report.broken_refs:
            lines.append(f"- `{b.source_id}` (`{b.source_path}`) -> **`{b.target_id}` (missing)**")
    else:
        lines.append("No broken refs")
    lines.append("")
    if report.orphan_docs:
        lines.append(f"## Orphan docs ({len(report.orphan_docs)})")
        for o in report.orphan_docs:
            lines.append(f"- `{o}`")
    else:
        lines.append("No orphan docs")
    lines.append("")
    if report.cycles:
        lines.append(f"## Cycles ({len(report.cycles)})")
        for c in report.cycles:
            lines.append("- " + " -> ".join(f"`{x}`" for x in c))
    else:
        lines.append("No cycles")
    return "\n".join(lines)


def format_answer_md(question: str, answer: Any) -> str:
    """Format a RAGPipeline Answer as markdown."""
    lines = [f"# Answer to: {question}", ""]
    if answer.is_dummy:
        lines.append("> _DUMMY mode (no ANTHROPIC_API_KEY)_\n")
    lines.append(answer.text)
    lines.append("")
    lines.append("## Sources")
    for s in answer.sources:
        marker = "* cited" if s.id in answer.cited_ids else ""
        lines.append(f"- `{s.id}` — {s.title} (score {s.score:.3f}) {marker}".strip())
    return "\n".join(lines)


def format_answer_json(question: str, answer: Any) -> str:
    """Format a RAGPipeline Answer as JSON."""
    payload = {
        "question": question,
        "answer": answer.text,
        "cited_ids": answer.cited_ids,
        "is_dummy": answer.is_dummy,
        "model": answer.model,
        "sources": [
            {"id": s.id, "title": s.title, "score": s.score, "axes": s.axes}
            for s in answer.sources
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def format_axes_md(axes: list[dict]) -> str:
    lines = ["# Available axes", ""]
    for a in axes:
        line = f"- **{a['name']}** ({a.get('type', 'string')}"
        if a.get("required"):
            line += ", required"
        line += ")"
        if a.get("values"):
            line += f" — values: {a['values']}"
        lines.append(line)
    return "\n".join(lines)


def format_documents_md(
    results: list[SearchResult],
    total: int,
    offset: int,
    has_more: bool,
    next_offset: int | None,
) -> str:
    lines = [f"# Documents (total={total}, offset={offset}, count={len(results)})"]
    if has_more:
        lines.append(f"\n_next offset: {next_offset}_\n")
    for r in results:
        lines.append(f"- `{r.id}` — {r.title} — axes: {r.axes}")
    return "\n".join(lines)
