"""Reference integrity checker for the knowledge base.

Validates that every `refs: [...]` entry in a document points to an existing
document id, and surfaces orphans / cycles for awareness.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from backend.src.loader import Document

logger = logging.getLogger(__name__)


@dataclass
class BrokenRef:
    source_id: str
    source_path: str
    target_id: str  # the missing one


@dataclass
class IntegrityReport:
    total_docs: int = 0
    total_refs: int = 0
    broken_refs: list[BrokenRef] = field(default_factory=list)
    orphan_docs: list[str] = field(default_factory=list)  # docs not referenced by anyone
    cycles: list[list[str]] = field(default_factory=list)  # simple cycle detection
    docs_by_id: dict[str, str] = field(default_factory=dict)  # id -> path

    @property
    def has_errors(self) -> bool:
        return bool(self.broken_refs)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_docs": self.total_docs,
            "total_refs": self.total_refs,
            "broken_refs": [
                {"source_id": b.source_id, "source_path": b.source_path, "target_id": b.target_id}
                for b in self.broken_refs
            ],
            "orphan_docs": self.orphan_docs,
            "cycles": self.cycles,
        }


def _find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Simple DFS cycle detection. Returns a list of cycle paths."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = defaultdict(int)
    cycles: list[list[str]] = []
    stack: list[str] = []

    def visit(node: str) -> None:
        if color[node] == GRAY:
            # Found cycle: rewind stack until we find node again
            idx = stack.index(node)
            cycles.append(stack[idx:] + [node])
            return
        if color[node] == BLACK:
            return
        color[node] = GRAY
        stack.append(node)
        for nxt in graph.get(node, []):
            visit(nxt)
        stack.pop()
        color[node] = BLACK

    for n in list(graph.keys()):
        if color[n] == WHITE:
            visit(n)
    return cycles


class IntegrityChecker:
    def check(self, docs: list[Document]) -> IntegrityReport:
        report = IntegrityReport(total_docs=len(docs))
        ids = {d.id for d in docs}
        report.docs_by_id = {d.id: str(d.path) for d in docs}

        referenced: set[str] = set()
        graph: dict[str, list[str]] = defaultdict(list)

        for d in docs:
            for r in d.refs:
                report.total_refs += 1
                referenced.add(r)
                graph[d.id].append(r)
                if r not in ids:
                    report.broken_refs.append(
                        BrokenRef(source_id=d.id, source_path=str(d.path), target_id=r)
                    )

        # orphan = doc not referenced by anyone (including itself)
        report.orphan_docs = sorted(d.id for d in docs if d.id not in referenced)

        # cycles
        report.cycles = _find_cycles(graph)

        return report


def format_report(report: IntegrityReport) -> str:
    lines: list[str] = []
    lines.append("=== Integrity Report ===")
    lines.append(f"Total documents: {report.total_docs}")
    lines.append(f"Total refs:      {report.total_refs}")
    lines.append("")
    if report.broken_refs:
        lines.append(f"[BROKEN] Broken refs: {len(report.broken_refs)}")
        for b in report.broken_refs:
            lines.append(f"  - {b.source_id} ({b.source_path}) -> {b.target_id} (missing)")
    else:
        lines.append("[OK] No broken refs")
    lines.append("")
    if report.orphan_docs:
        lines.append(f"[WARN] Orphan docs (not referenced): {len(report.orphan_docs)}")
        for o in report.orphan_docs:
            lines.append(f"  - {o}")
    else:
        lines.append("[OK] No orphan docs")
    lines.append("")
    if report.cycles:
        lines.append(f"[WARN] Cycles: {len(report.cycles)}")
        for c in report.cycles:
            lines.append("  - " + " -> ".join(c))
    else:
        lines.append("[OK] No cycles")
    return "\n".join(lines)


def _main(argv: list[str]) -> int:
    import argparse
    import json
    from pathlib import Path

    from backend.src.config import configure_logging
    from backend.src.loader import load_directory

    configure_logging()
    p = argparse.ArgumentParser()
    p.add_argument("knowledge_dir", type=Path)
    p.add_argument("--json", action="store_true", help="Output JSON instead of text")
    p.add_argument("--strict", action="store_true", help="Exit 1 if broken refs found")
    args = p.parse_args(argv[1:])

    docs = load_directory(args.knowledge_dir)
    report = IntegrityChecker().check(docs)

    if args.json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_report(report))

    if args.strict and report.has_errors:
        return 1
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv))
